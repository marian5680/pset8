import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = []
    cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    grand_total = cash[0]["cash"]
    rows = db.execute("SELECT symbol, sum(shares) total from transactions where userid = ? group by symbol order by symbol", session["user_id"])#
    for row in rows:
        stock = {}
        stock["symbol"] = row["symbol"]
        stock["shares"] = row["total"]

        quote = lookup(row["symbol"])
        stock["name"] = quote["name"]
        stock ["price"] = usd(quote["price"])

        stock["value"] = usd(quote["price"] * stock["shares"])
        stocks.append(stock)
        grand_total += (quote["price"] * stock["shares"])

    return render_template("index.html", cash=usd(cash[0]["cash"]), stocks=stocks, grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("Sorry that symbol cannot be found.", 403)
        symbol = quote["symbol"]
        price = quote["price"]
        numshares = int(request.form.get("quantity"))
        cost = price * numshares
        row = db.execute("SELECT cash from users where id = ?", session["user_id"])
        cash = row[0]["cash"]

        if cash >= cost:

            cash -= cost

            row = db.execute("INSERT INTO transactions (userid, symbol, shares, price) VALUES (:userid, :symbol, :numshares, :price)",
                        userid=session["user_id"], symbol=symbol, numshares=numshares, price=price)

            row = db.execute("UPDATE users set cash = :cash where id = :userid", cash=cash, userid=session["user_id"])

            return redirect("/")

        else:
            return apology("You do not have enough cash to make this transaction.", 403)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    stocks = db.execute("SELECT symbol, shares, price, time from transactions where userid=:userid order by time desc;", userid=session["user_id"])
    for stock in stocks:
        stock["price"] = usd(stock["price"])

    return render_template("history.html", stocks=stocks)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("Sorry that symbol cannot be found.", 403)
        name = quote["name"]
        symbol = quote["symbol"]
        price = usd(quote["price"])
        return render_template("rtn_quote.html", name=name, symbol=symbol, price=price)
    else:
        return render_template("get_quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username=request.form.get("username")
        password = request.form.get("password")

        # Ensure username was submitted
        if not username:
            return apology("Must provide username", 403)

        # Ensure password was submitted
        elif not password:
            return apology("Must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)

        # Ensure username does not exists
        if len(rows) >= 1:
            return apology("Username is already in use", 403)

        # Insert new record into user table
        id = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                          username=username, hash=generate_password_hash(password))

        if id <= 0:
            return apology("Registration failed", 403)

        # Redirect user to login page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        value = request.form.get("symbol").split(',')
        symbol = value[0]
        numshares=int(request.form.get("quantity"))

        quote = lookup(symbol)
        if (quote == None):
            return apology(symbol + " cannot be found.")
        symbol = quote["symbol"]
        price = quote["price"]
        earned = price * numshares

        # record number of shares as a negative
        numshares = 0 - numshares

        row = db.execute("SELECT cash from users where id = ?", session["user_id"])
        cash = row[0]["cash"]

        cash += earned

        row = db.execute("INSERT INTO transactions (userid, symbol, shares, price) VALUES (:userid, :symbol, :numshares, :price)",
                        userid=session["user_id"], symbol=symbol, numshares=numshares, price=price)

        row = db.execute("UPDATE users set cash = :cash where id = :userid", cash=cash, userid=session["user_id"])

        return redirect("/")
    else:
        stocks = db.execute("SELECT symbol, sum(shares) shares from transactions where userid = ? group by symbol order by symbol", session["user_id"])
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
