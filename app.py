import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")


# Create default admin account
def create_admin():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE username=%s", ("admin",))

    if not cursor.fetchone():
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        password = generate_password_hash(admin_pass)
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            ("admin", password)
        )
        db.commit()

    cursor.close()
    db.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


# Login
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password", "danger")

    return render_template("login.html")


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM books")
    total_books = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM issued_books WHERE status='Issued'")
    issued_books = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(quantity) FROM books")
    available_books = cursor.fetchone()[0] or 0

    cursor.close()
    db.close()

    return render_template(
        "dashboard.html",
        total_books=total_books,
        total_students=total_students,
        issued_books=issued_books,
        available_books=available_books
    )


# Books
@app.route("/books", methods=["GET", "POST"])
@login_required
def books():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()

        try:
            quantity = int(request.form.get("quantity", -1))
        except ValueError:
            quantity = -1

        if title and author and quantity >= 0:
            cursor.execute(
                """INSERT INTO books(title, author, category, quantity)
                   VALUES(%s, %s, %s, %s)""",
                (title, author, category, quantity)
            )
            db.commit()
            flash("Book added successfully", "success")
        else:
            flash("Please enter valid book details", "danger")

        cursor.close()
        db.close()
        return redirect(url_for("books"))

    search = request.args.get("search", "").strip()

    cursor.execute(
        """SELECT * FROM books
           WHERE title LIKE %s OR author LIKE %s
           ORDER BY id DESC""",
        (f"%{search}%", f"%{search}%")
    )
    book_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("books.html", books=book_list, search=search)


@app.route("/delete_book/<int:id>", methods=["POST"])
@login_required
def delete_book(id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM issued_books WHERE book_id=%s AND status='Issued'",
            (id,)
        )
        if cursor.fetchone():
            flash("Book is currently issued to a student and cannot be deleted", "danger")
        else:
            cursor.execute("DELETE FROM issued_books WHERE book_id=%s", (id,))
            cursor.execute("DELETE FROM books WHERE id=%s", (id,))
            db.commit()
            flash("Book deleted successfully", "success")
    except Exception:
        db.rollback()
        flash("Error deleting book", "danger")

    cursor.close()
    db.close()
    return redirect(url_for("books"))


# Students
@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        mobile = request.form.get("mobile", "").strip()
        class_name = request.form.get("class_name", "").strip()

        if name:
            cursor.execute(
                """INSERT INTO students(name, email, mobile, class_name)
                   VALUES(%s, %s, %s, %s)""",
                (name, email, mobile, class_name)
            )
            db.commit()
            flash("Student added successfully", "success")
        else:
            flash("Student name is required", "danger")

        cursor.close()
        db.close()
        return redirect(url_for("students"))

    cursor.execute("SELECT * FROM students ORDER BY id DESC")
    student_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("students.html", students=student_list)


@app.route("/delete_student/<int:id>", methods=["POST"])
@login_required
def delete_student(id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM issued_books WHERE student_id=%s AND status='Issued'",
            (id,)
        )
        if cursor.fetchone():
            flash("Student has unreturned books and cannot be deleted", "danger")
        else:
            cursor.execute("DELETE FROM issued_books WHERE student_id=%s", (id,))
            cursor.execute("DELETE FROM students WHERE id=%s", (id,))
            db.commit()
            flash("Student deleted successfully", "success")
    except Exception:
        db.rollback()
        flash("Error deleting student", "danger")

    cursor.close()
    db.close()
    return redirect(url_for("students"))


# Issue Book (With Fine Calculation & Return History)
@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        try:
            book_id = int(request.form["book_id"])
            student_id = int(request.form["student_id"])

            db.start_transaction()

            cursor.execute(
                "SELECT quantity FROM books WHERE id=%s FOR UPDATE",
                (book_id,)
            )
            book = cursor.fetchone()

            cursor.execute(
                "SELECT id FROM students WHERE id=%s",
                (student_id,)
            )
            student = cursor.fetchone()

            if not book or book["quantity"] <= 0:
                raise ValueError("Book is not available")

            if not student:
                raise ValueError("Student not found")

            cursor.execute(
                """SELECT id FROM issued_books 
                   WHERE book_id=%s AND student_id=%s AND status='Issued'""",
                (book_id, student_id)
            )
            if cursor.fetchone():
                raise ValueError("This book is already issued to this student")

            issue_date = date.today()
            due_date = issue_date + timedelta(days=14)

            cursor.execute(
                "UPDATE books SET quantity=quantity-1 WHERE id=%s",
                (book_id,)
            )

            cursor.execute(
                """INSERT INTO issued_books
                   (book_id, student_id, issue_date, due_date)
                   VALUES (%s, %s, %s, %s)""",
                (book_id, student_id, issue_date, due_date)
            )

            db.commit()
            flash("Book issued successfully", "success")

        except Exception as e:
            db.rollback()
            flash(str(e), "danger")

        cursor.close()
        db.close()
        return redirect(url_for("issue"))

    cursor.execute("SELECT * FROM books WHERE quantity > 0")
    book_list = cursor.fetchall()

    cursor.execute("SELECT * FROM students ORDER BY name")
    student_list = cursor.fetchall()

    cursor.execute("""
        SELECT i.id, b.title, s.name, i.issue_date, i.due_date
        FROM issued_books i
        JOIN books b ON i.book_id = b.id
        JOIN students s ON i.student_id = s.id
        WHERE i.status='Issued'
        ORDER BY i.id DESC
    """)
    issued_list = cursor.fetchall()

    today = date.today()
    fine_per_day = 5

    for row in issued_list:
        if row["due_date"] and today > row["due_date"]:
            overdue_days = (today - row["due_date"]).days
            row["overdue_days"] = overdue_days
            row["fine"] = overdue_days * fine_per_day
        else:
            row["overdue_days"] = 0
            row["fine"] = 0

    cursor.execute("""
        SELECT i.id, b.title, s.name, i.issue_date, i.due_date, i.return_date
        FROM issued_books i
        JOIN books b ON i.book_id = b.id
        JOIN students s ON i.student_id = s.id
        WHERE i.status='Returned'
        ORDER BY i.return_date DESC, i.id DESC
        LIMIT 25
    """)
    returned_list = cursor.fetchall()

    for row in returned_list:
        if row["return_date"] and row["due_date"] and row["return_date"] > row["due_date"]:
            late_days = (row["return_date"] - row["due_date"]).days
            row["fine_paid"] = late_days * fine_per_day
        else:
            row["fine_paid"] = 0

    cursor.close()
    db.close()

    return render_template(
        "issue.html",
        books=book_list,
        students=student_list,
        issued=issued_list,
        returned=returned_list,
        today=today
    )


# Return Book
@app.route("/return_book/<int:id>", methods=["POST"])
@login_required
def return_book(id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        db.start_transaction()

        cursor.execute(
            "SELECT book_id, due_date, status FROM issued_books WHERE id=%s FOR UPDATE",
            (id,)
        )
        record = cursor.fetchone()

        if not record or record["status"] != "Issued":
            raise ValueError("Invalid or already returned book")

        today = date.today()
        fine = 0
        if record["due_date"] and today > record["due_date"]:
            fine = (today - record["due_date"]).days * 5

        cursor.execute(
            """UPDATE issued_books
               SET status='Returned', return_date=%s
               WHERE id=%s""",
            (today, id)
        )

        cursor.execute(
            "UPDATE books SET quantity=quantity+1 WHERE id=%s",
            (record["book_id"],)
        )

        db.commit()
        if fine > 0:
            flash(f"Book returned successfully. Late Fine Collected: ₹{fine}", "success")
        else:
            flash("Book returned on time (No fine)", "success")

    except Exception as e:
        db.rollback()
        flash(str(e), "danger")

    cursor.close()
    db.close()

    return redirect(url_for("issue"))


if __name__ == "__main__":
    create_admin()
    app.run(debug=True)