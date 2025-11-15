# Banking-Mangement-System-
A complete Banking Management System built with Python, Tkinter, and SQLite. Features include account creation, secure login, deposit/withdraw/transfer operations, transaction history, CSV/PDF export, and a clean GUI-based workflow.

The Banking Management System is a GUI-based desktop application built in Python, designed to simulate real-world banking operations in a simple and user-friendly interface. The system uses SQLite for secure and persistent data storage and provides all essential banking functionalities, including:

Account Management
Create, quick-create, search, view, and delete customer accounts with auto-generated account numbers.

Secure Authentication
PINs are hashed using SHA-256 (demo implementation).
Production-ready hashing (bcrypt/argon2) can be integrated easily.

Banking Operations
Perform deposits, withdrawals, and account-to-account transfers with full validation.

Transaction Tracking
Every action is logged and displayed in a detailed history table.

Data Export
Export transaction history to CSV and optionally generate PDF receipts (via ReportLab).

Python 3

Tkinter (GUI)

SQLite (Database)

ReportLab (optional PDF export)

This project is ideal for learning GUI programming, database integration, financial system logic, and secure authentication techniques in Python
