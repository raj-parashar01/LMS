📚 Library Desk — Library Management SystemLibrary Desk is a full-stack Library Management System built for academic institutions to streamline book cataloging, student registration, and daily circulation workflows. Powered by Flask and MySQL, it enforces transactional stock integrity and automates late-return fine calculation.Key CapabilitiesModuleFunctionalityAuthenticationSession-protected admin portal with password hashing (Werkzeug) and auto-seeded default admin user.DashboardLive operational metrics covering total book titles, available shelf copies, active loans, and student count.Book InventoryAdd new books, search catalog by title/author, track real-time stock, and safely block deletion of issued books.Student RecordsRegister student profiles with course/class info and prevent removal of accounts with pending returns.Circulation Desk14-day loan assignment with row-level locking (FOR UPDATE), duplicate issue checks, ₹5/day overdue fine calculation, and return history logs.Application RoutesRouteMethodsAccessDescription/ , /loginGET, POSTPublicAdmin sign-in page/logoutGETProtectedClears active session/dashboardGETProtectedSystem KPIs and quick actions/booksGET, POSTProtectedView, search, and add books/delete_book/<id>POSTProtectedDelete unissued book record/studentsGET, POSTProtectedView and register students/delete_student/<id>POSTProtectedDelete student without active loans/issueGET, POSTProtectedIssue books, view live fines & return logs/return_book/<id>POSTProtectedProcess book return and restore stockQuick Start Guide1. Clone & Set Up Environmentgit clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt

2. Environment ConfigurationCreate a .env file in the root folder:SECRET_KEY=replace_with_random_secret_key
ADMIN_PASSWORD=Admin@123
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=library_db

3. Initialize MySQL DatabaseRun the following SQL script in your MySQL client:CREATE DATABASE IF NOT EXISTS library_db;
USE library_db;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    quantity INT NOT NULL DEFAULT 0
);

CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150),
    mobile VARCHAR(20),
    class_name VARCHAR(100)
);

CREATE TABLE issued_books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    book_id INT NOT NULL,
    student_id INT NOT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    return_date DATE DEFAULT NULL,
    status ENUM('Issued', 'Returned') DEFAULT 'Issued',
    FOREIGN KEY (book_id) REFERENCES books(id),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

4. Launch Serverpython app.py

Visit http://127.0.0.1:5000 and log in with:
Username: admin
Password: Admin@123 (or your configured ADMIN_PASSWORD)
Directory Layout
├── app.py              # Flask routes, auth & transaction logic
├── database.py         # MySQL connection configuration
├── requirements.txt    # Python package dependencies
├── .gitignore          # Excluded environment & cache files
├── static/
│   └── style.css       # Clean UI stylesheet
└── templates/
    ├── base.html       # Shared navigation & alert layout
    ├── login.html      # Authentication view
    ├── dashboard.html  # Overview metrics
    ├── books.html      # Book catalog & search
    ├── students.html   # Student directory
    └── issue.html      # Circulation, fines & return history
