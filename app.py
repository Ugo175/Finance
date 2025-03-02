import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    try:
        """Show portfolio of stocks"""
        user_id = session["user_id"]

        # Query database for user's stocks
        rows = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=user_id)

        # Query database for user's current cash balance
        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=user_id)[0]["cash"]

        # Prepare a list to hold stock information
        stocks = []
        total_value = 0

        # Iterate over each stock the user owns
        for row in rows:
            symbol = row["symbol"]
            shares = row["total_shares"]
            stock = lookup(symbol)
            current_price = stock["price"]
            total_stock_value = shares * current_price

            # Add the stock info to the list
            stocks.append({
                "symbol": symbol,
                "name": stock["name"],
                "shares": shares,
                "price": usd(current_price),
                "total": usd(total_stock_value)
            })

            total_value += total_stock_value

        # Calculate grand total (cash + total stock value)
        grand_total = user_cash + total_value

        return render_template("index.html", stocks=stocks, cash=usd(user_cash), total=usd(grand_total))

    except:
        return apology("TODO")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "GET":
        return render_template("buy.html")

    elif request.method == "POST":
        try:
            symbol = request.form.get("symbol")
            if not symbol:
                return apology("missing symbol")

            shares = request.form.get("shares")
            if not shares or int(shares) <= 0:
                return apology("invalid number of shares")

            # Add your logic here to handle buying stocks
            stock_details = lookup(symbol)
            if not stock_details:
                return apology("invalid stock symbol")

            # Ensure shares is an integer
            shares = int(shares)

            # Get the user's remaining cash
            rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
            if len(rows) != 1:
                return apology("user not found")
            remaining_cash = rows[0]["cash"]

            # Get the current price of the stock
            current_price = stock_details['price']

            # Calculate the total cost
            total_cost = current_price * shares

            # Check if the user has enough cash
            if total_cost > remaining_cash:
                return apology("Not enough funds")

            # Deduct the total cost from the user's cash
            db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_cost, session["user_id"])

            # Insert the purchase into the purchases table
            db.execute("INSERT INTO purchases (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                       session["user_id"], symbol, shares, current_price)

            # Redirect to the homepage or render a success message
            return redirect("/")

        except Exception as e:
            return apology(str(e))

    return redirect("/")




@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]

    try:
        # Query database for user's purchase transactions
        purchases = db.execute("SELECT symbol, shares, price, timestamp FROM purchases WHERE user_id = :user_id ORDER BY transacted ASC", user_id=user_id)

        # Query database for user's sale transactions
        sales = db.execute("SELECT symbol, shares, price, timestamp FROM sales WHERE user_id = :user_id ORDER BY transacted ASC", user_id=user_id)

        # Combine purchases and sales into a single list of transactions
        transactions = []

        for purchase in purchases:
            transactions.append({
                "symbol": purchase["symbol"],
                "shares": purchase["shares"],
                "price": purchase["price"],
                "timestamp": purchase["timestamp"],
                "type": "BUY"
            })

        for sale in sales:
            transactions.append({
                "symbol": sale["symbol"],
                "shares": sale["shares"],
                "price": sale["price"],
                "timestamp": sale["timestamp"],
                "type": "SELL"
            })

        # Sort transactions by the transacted timestamp
        transactions.sort(key=lambda x: x["timestamp"])

        return render_template("history.html", transactions=transactions)

    except Exception as e:
        return apology("Page not found", code=403)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")



@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    elif request.method == "POST":
        try:
            symbol = request.form.get("symbol")
            if not symbol:
                return apology("missing symbol")
            return render_template("quoted.html", symbol=symbol)
        except:
            return apology("Ensure symbol is the correct format")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        try:
            # Get the form data
            username = request.form.get("username")
            password = request.form.get("password")
            confirmation = request.form.get("confirmation")


            # Validate the username and password
            if not username or not password:
                return render_template("apology.html", message="All fields are required")
            if password != confirmation:
                return render_template("apology.html", message="Passwords do not match")

            # Hash the password
            hashed_password = generate_password_hash(password)

            # Insert into the database
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()

            # Redirect to the login page
            return redirect("/login")

            # If duplicate values are detected by the database for either username or password or both
        except ValueError:
                return render_template("apology.html", message="Username or Password already taken")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        return render_template("sell.html")

    elif request.method == "POST":
        try:
            shares = request.form.get("shares")
            if not shares:
                return apology("missing symbol")

        except as e:
            return apology("Invalid request", code=400)

    return redirect("/")
