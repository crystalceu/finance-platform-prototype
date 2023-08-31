import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    #"""Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    #"""Show portfolio of stocks"""
    rows = db.execute("SELECT * FROM savings WHERE buyer_id = (?)", session["user_id"])
    shares_price = 0

    for row in rows:
        price = lookup(row["symbol"])
        row["price"] = price["price"]
        row["name"] = price["name"]
        shares_price += price["price"] * row["number"]

    moneys = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    money = moneys[0]["cash"]
    return render_template("index.html", savings=rows, money=money, shares_price=shares_price)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    #"""Buy shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 400)

        # Ensure shares was submitted
        if not (request.form.get("shares")).isdigit():
            return apology("must be integer", 400)

        # Ensure shares are positive
        elif int(request.form.get("shares")) < 0:
            return apology("number of shares must be positive", 400)

        # Ensure there are any shares(not zero)
        elif int(request.form.get("shares")) == 0:
            return apology("buy zero shares is not possible", 400)

        symbol = lookup(request.form.get("symbol"))
        rows = db.execute("SELECT * FROM users WHERE id = (?)", session["user_id"])

        # Ensure symbol is correct and exist on IEX
        if symbol == None:
            return apology("symbol is not correct", 400)

        # Ensure the user money is enough to buy shares
        elif symbol["price"] * float(request.form.get("shares")) > rows[0]["cash"]:
            return apology("not enough money", 400)

        # Insert new transaction into transactions, it is a buy transaction and the user spend the money
        db.execute("""INSERT INTO transactions (hash, buyer_id, symbol, number, cost, time, type) VALUES (datetime(), ?, ?, ?, ?, datetime(), "-")""",
                   rows[0]["id"],
                   request.form.get("symbol"),
                   request.form.get("shares"),
                   float(symbol["price"]) * float(request.form.get("shares")))

        # Update users availible cash in table users
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?",
                   symbol["price"] * float(request.form.get("shares")), session["user_id"])

        savingsrows = db.execute("SELECT * FROM savings WHERE (buyer_id = ? AND symbol = ?)",
                                 session["user_id"], request.form.get("symbol"))

        # If user already had shares of this company, we just update their number
        if len(savingsrows) != 0:
            db.execute("UPDATE savings SET number = number + ? WHERE (buyer_id = ? AND symbol = ?)",
                       request.form.get("shares"), session["user_id"], request.form.get("symbol"))

        # If user buy shares of this company for the first time, then we add new line into the savings table
        else:
            db.execute("INSERT INTO savings (buyer_id, symbol, number) VALUES (?, ?, ?)",
                       session["user_id"], request.form.get("symbol"), request.form.get("shares"))

        buyrows = db.execute("SELECT * FROM transactions ORDER BY time DESC LIMIT 1")
        buyrows[0]["name"] = symbol["name"]
        buyrows[0]["price"] = symbol["price"]

        moneys = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        money = moneys[0]["cash"]

        # If the buy transaction was made from the index.html, then we return the user to index.html
        if request.form.get("home") == "index":
            return redirect("/")

        return render_template("buyed.html", buyrows=buyrows[0], money=money)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    #"""Show history of transactions"""
    rows = db.execute("SELECT * FROM transactions WHERE buyer_id = ?", session["user_id"])

    for row in rows:
        name = lookup(row["symbol"])
        row["name"] = name["name"]

    return render_template("history.html", transactions=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    #"""Log user in"""

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
    #"""Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/chngpassword", methods=["GET", "POST"])
def chngpassword():
    #"""Change the password"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure new password was submitted
        elif not request.form.get("newpassword"):
            return apology("must provide newpassword", 400)

        # Ensure new password confirmation was submitted
        elif not request.form.get("newpassword_confirmation"):
            return apology("must provide newpassword_confirmation", 403)

        # Query database for username and hash
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        # Ensure the current username was submitted correctly
        if request.form.get("username") != rows[0]["username"]:
            return apology("current username is incorrect", 400)

        # Ensure the current password was submitted correctly
        elif not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("current password is incorrect", 400)

        # Ensure the new password was repeated correctly
        elif request.form.get("newpassword") != request.form.get("newpassword_confirmation"):
            return apology("new password must be the same", 400)

        db.execute("UPDATE users SET hash = ? WHERE id = ?",
                   generate_password_hash(request.form.get("newpassword"), method='pbkdf2:sha256', salt_length=8), session["user_id"])

        return redirect("/")

    else:
        return render_template("chngpassword.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    #"""Get stock quote."""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        quotes = lookup(request.form.get("symbol"))

        # If symbol was not correct return apology
        if quotes == None:
            return apology("symbol is not correct", 400)

        return render_template("quote.html", quotes=quotes)
    else:
        return render_template("quoted.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    #"""Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure the password was repeated correctly
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must be the same", 400)

        userrows = db.execute("SELECT * FROM users WHERE username = (?)", request.form.get("username"))

        # Ensure username is unique
        if len(userrows) != 0:
            return apology("username is already exits", 400)

        # Insert new user to database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"),
                   generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8))

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    #"""Sell shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure shares was submitted
        elif not request.form.get("shares").isdigit():
            return apology("shares should be integer", 400)

        # Ensure shares are positive
        elif int(request.form.get("shares")) < 0:
            return apology("number of shares must be positive", 400)

        # Ensure there are more than zero shares
        elif int(request.form.get("shares")) == 0:
            return apology("sell zero shares is not possible", 400)

        price = lookup(request.form.get("symbol"))
        number = db.execute("SELECT number FROM savings WHERE buyer_id = ? AND symbol = ?",
                            session["user_id"], request.form.get("symbol"))

        # Ensure the user try to sell no more shares than he has
        if int(request.form.get("shares")) > number[0]["number"]:
            return apology("not enough shares", 400)

        # If user sell all the shares by this symbol, then we delete the line with this symbol from savings table
        if int(request.form.get("shares")) == number[0]["number"]:
            db.execute("DELETE FROM savings WHERE (buyer_id = ? AND symbol = ?)",
                       session["user_id"], request.form.get("symbol"))

        if int(request.form.get("shares")) < number[0]["number"]:
            db.execute("UPDATE savings SET number = number - ? WHERE (buyer_id = ? AND symbol = ?)",
                       int(request.form.get("shares")), session["user_id"], request.form.get("symbol"))

        # Insert new transaction to transactions table
        db.execute("""INSERT INTO transactions (hash, buyer_id, symbol, number, cost, time, type) VALUES (datetime(), ?, ?, ?, ?, datetime(), "+")""",
                   session["user_id"], request.form.get("symbol"), request.form.get("shares"), (price["price"] * float(request.form.get("shares"))))

        # Update the increased cash in users table
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?",
                   price["price"] * float(request.form.get("shares")), session["user_id"])

        sellrows = db.execute("SELECT * FROM transactions ORDER BY time DESC LIMIT 1")
        sellrows[0]["name"] = price["name"]
        sellrows[0]["price"] = price["price"]

        moneys = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        money = moneys[0]["cash"]

        # If the sell transactions was called from index.html, then we return user to the index.html
        if request.form.get("home") == "index":
            return redirect("/")

        return render_template("buyed.html", buyrows=sellrows[0], money=money)

    else:
        symbols = db.execute("SELECT symbol FROM savings WHERE buyer_id = ?", session["user_id"])
        result = []

        for symbol in symbols:
            result.append(symbol["symbol"])

        return render_template("sell.html", symbols=result)