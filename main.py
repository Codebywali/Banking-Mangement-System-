import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import hashlib
import random
import string
import datetime
import csv
import os

# Optional reportlab import
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdfcanvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

DB_FILE = "banking.db"

# ------------------------- Database helpers -------------------------
class DB:
    def __init__(self, path=DB_FILE):
        self.conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self):
        cur = self.conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                account_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_no TEXT NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                counterparty TEXT,
                timestamp TIMESTAMP NOT NULL,
                note TEXT,
                FOREIGN KEY(account_no) REFERENCES accounts(account_no)
            )
        ''')
        self.conn.commit()

    def create_account(self, name, pin, initial_deposit=0.0):
        account_no = self._generate_account_no()
        pin_hash = self._hash_pin(pin)
        now = datetime.datetime.utcnow()
        cur = self.conn.cursor()
        cur.execute('INSERT INTO accounts(account_no,name,pin_hash,balance,created_at) VALUES (?,?,?,?,?)',
                    (account_no, name, pin_hash, float(initial_deposit), now))
        if float(initial_deposit) > 0:
            cur.execute('INSERT INTO transactions(account_no,type,amount,counterparty,timestamp,note) VALUES (?,?,?,?,?,?)',
                        (account_no, 'deposit', float(initial_deposit), None, now, 'Initial deposit'))
        self.conn.commit()
        return account_no

    def delete_account(self, account_no):
        cur = self.conn.cursor()
        cur.execute('DELETE FROM transactions WHERE account_no=?', (account_no,))
        cur.execute('DELETE FROM accounts WHERE account_no=?', (account_no,))
        self.conn.commit()

    def list_accounts(self, search=None):
        cur = self.conn.cursor()
        if search:
            q = f"%{search}%"
            cur.execute('SELECT * FROM accounts WHERE account_no LIKE ? OR name LIKE ? ORDER BY created_at DESC', (q,q))
        else:
            cur.execute('SELECT * FROM accounts ORDER BY created_at DESC')
        return cur.fetchall()

    def get_account(self, account_no):
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM accounts WHERE account_no=?', (account_no,))
        return cur.fetchone()

    def authenticate(self, account_no, pin):
        acc = self.get_account(account_no)
        if not acc:
            return False
        return acc['pin_hash'] == self._hash_pin(pin)

    def deposit(self, account_no, amount, note=None):
        if amount <= 0:
            raise ValueError('Deposit amount must be positive')
        cur = self.conn.cursor()
        cur.execute('UPDATE accounts SET balance = balance + ? WHERE account_no=?', (amount, account_no))
        now = datetime.datetime.utcnow()
        cur.execute('INSERT INTO transactions(account_no,type,amount,timestamp,note) VALUES (?,?,?,?,?)',
                    (account_no, 'deposit', amount, now, note))
        self.conn.commit()

    def withdraw(self, account_no, amount, note=None):
        if amount <= 0:
            raise ValueError('Withdraw amount must be positive')
        acc = self.get_account(account_no)
        if not acc:
            raise ValueError('Account not found')
        if acc['balance'] < amount:
            raise ValueError('Insufficient funds')
        cur = self.conn.cursor()
        cur.execute('UPDATE accounts SET balance = balance - ? WHERE account_no=?', (amount, account_no))
        now = datetime.datetime.utcnow()
        cur.execute('INSERT INTO transactions(account_no,type,amount,timestamp,note) VALUES (?,?,?,?,?)',
                    (account_no, 'withdraw', amount, now, note))
        self.conn.commit()

    def transfer(self, from_acc, to_acc, amount, note=None):
        if amount <= 0:
            raise ValueError('Transfer amount must be positive')
        if from_acc == to_acc:
            raise ValueError('Cannot transfer to the same account')
        fa = self.get_account(from_acc)
        ta = self.get_account(to_acc)
        if not fa or not ta:
            raise ValueError('Source or destination account not found')
        if fa['balance'] < amount:
            raise ValueError('Insufficient funds')
        cur = self.conn.cursor()
        now = datetime.datetime.utcnow()
        cur.execute('UPDATE accounts SET balance = balance - ? WHERE account_no=?', (amount, from_acc))
        cur.execute('UPDATE accounts SET balance = balance + ? WHERE account_no=?', (amount, to_acc))
        cur.execute('INSERT INTO transactions(account_no,type,amount,counterparty,timestamp,note) VALUES (?,?,?,?,?,?)',
                    (from_acc, 'transfer_out', amount, to_acc, now, note))
        cur.execute('INSERT INTO transactions(account_no,type,amount,counterparty,timestamp,note) VALUES (?,?,?,?,?,?)',
                    (to_acc, 'transfer_in', amount, from_acc, now, note))
        self.conn.commit()

    def get_transactions(self, account_no, limit=500):
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM transactions WHERE account_no=? ORDER BY timestamp DESC LIMIT ?', (account_no, limit))
        return cur.fetchall()

    def export_transactions_csv(self, account_no, filepath):
        rows = self.get_transactions(account_no, limit=1000000)
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id','account_no','type','amount','counterparty','timestamp','note'])
            for r in rows:
                writer.writerow([r['id'], r['account_no'], r['type'], r['amount'], r['counterparty'], r['timestamp'], r['note']])

    def export_transaction_pdf(self, tx_row, filepath):
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError('reportlab not installed')
        c = pdfcanvas.Canvas(filepath, pagesize=letter)
        w, h = letter
        y = h - 72
        c.setFont('Helvetica-Bold', 14)
        c.drawString(72, y, 'Transaction Receipt')
        y -= 28
        c.setFont('Helvetica', 11)
        for k in ['id','account_no','type','amount','counterparty','timestamp','note']:
            v = tx_row[k]
            c.drawString(72, y, f"{k}: {v}")
            y -= 18
        c.showPage()
        c.save()

    def _generate_account_no(self):
        # 10-digit unique-ish account number
        while True:
            acct = ''.join(random.choices(string.digits, k=10))
            if not self.get_account(acct):
                return acct

    def _hash_pin(self, pin):
        # Simple SHA-256 for demo only. Use bcrypt/argon2 in production.
        if isinstance(pin, str):
            pin = pin.encode('utf-8')
        return hashlib.sha256(pin).hexdigest()

# ------------------------- GUI -------------------------

class BankingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Banking Management System')
        self.geometry('900x600')
        self.db = DB()
        self.current_account = None
        self._build_ui()

    def _build_ui(self):
        # Left pane: actions
        left = ttk.Frame(self)
        left.pack(side='left', fill='y', padx=8, pady=8)

        ttk.Label(left, text='Accounts').pack(pady=(0,6))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(left, textvariable=self.search_var)
        search_entry.pack(fill='x')
        ttk.Button(left, text='Search', command=self.refresh_account_list).pack(fill='x', pady=4)
        ttk.Button(left, text='Refresh', command=self.refresh_account_list).pack(fill='x', pady=2)
        ttk.Button(left, text='Quick Create', command=self.quick_create).pack(fill='x', pady=6)
        ttk.Button(left, text='Create Account', command=self.create_account_dialog).pack(fill='x', pady=2)
        ttk.Button(left, text='Delete Account', command=self.delete_selected_account).pack(fill='x', pady=2)

        ttk.Separator(left).pack(fill='x', pady=6)
        ttk.Label(left, text='Login').pack(pady=(4,2))
        self.login_acc_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.login_acc_var).pack(fill='x')
        self.login_pin_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.login_pin_var, show='*').pack(fill='x')
        ttk.Button(left, text='Login', command=self.login).pack(fill='x', pady=4)
        ttk.Button(left, text='Logout', command=self.logout).pack(fill='x', pady=2)

        ttk.Separator(left).pack(fill='x', pady=6)
        ttk.Button(left, text='Export Transactions CSV', command=self.export_csv_selected).pack(fill='x', pady=2)

        # Accounts list
        self.accounts_listbox = tk.Listbox(left, width=25, height=20)
        self.accounts_listbox.pack(pady=6)
        self.accounts_listbox.bind('<<ListboxSelect>>', self.on_account_select)

        # Right pane: main area
        right = ttk.Frame(self)
        right.pack(side='left', fill='both', expand=True, padx=8, pady=8)

        # Account details / operations
        self.header_label = ttk.Label(right, text='No account selected', font=('Helvetica', 14, 'bold'))
        self.header_label.pack(anchor='w')

        self.balance_var = tk.StringVar(value='')
        ttk.Label(right, textvariable=self.balance_var, font=('Helvetica', 12)).pack(anchor='w', pady=(4,8))

        ops_frame = ttk.Frame(right)
        ops_frame.pack(fill='x')

        ttk.Button(ops_frame, text='Deposit', command=self.deposit_dialog).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(ops_frame, text='Withdraw', command=self.withdraw_dialog).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(ops_frame, text='Transfer', command=self.transfer_dialog).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(ops_frame, text='View History', command=self.view_history).grid(row=0, column=3, padx=4, pady=4)

        # History table
        self.tree = ttk.Treeview(right, columns=('id','type','amount','counterparty','timestamp','note'), show='headings')
        for c in self.tree['columns']:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120, anchor='center')
        self.tree.pack(fill='both', expand=True, pady=(8,0))
        self.tree.bind('<Double-1>', self.on_tx_double)

        self.refresh_account_list()

    # ---------------- UI actions ----------------
    def refresh_account_list(self):
        search = self.search_var.get().strip()
        rows = self.db.list_accounts(search=search if search else None)
        self.accounts_listbox.delete(0, 'end')
        for r in rows:
            display = f"{r['account_no']} — {r['name']} (Bal: {r['balance']:.2f})"
            self.accounts_listbox.insert('end', display)

    def on_account_select(self, event=None):
        sel = self.accounts_listbox.curselection()
        if not sel:
            return
        text = self.accounts_listbox.get(sel[0])
        acct_no = text.split(' ')[0]
        self.show_account(acct_no)

    def show_account(self, account_no):
        acc = self.db.get_account(account_no)
        if not acc:
            messagebox.showerror('Error','Account not found')
            return
        self.header_label.config(text=f"{acc['account_no']} — {acc['name']}")
        self.balance_var.set(f"Balance: {acc['balance']:.2f}")
        self.current_account = acc['account_no']
        self.view_history()

    def create_account_dialog(self):
        dlg = CreateAccountDialog(self, self.db)
        self.wait_window(dlg)
        self.refresh_account_list()

    def quick_create(self):
        name = 'QuickUser_' + ''.join(random.choices(string.ascii_letters, k=5))
        pin = ''.join(random.choices(string.digits, k=4))
        acct = self.db.create_account(name, pin, initial_deposit=0.0)
        messagebox.showinfo('Quick Create', f'Created account {acct}\nPIN: {pin} (store it!)')
        self.refresh_account_list()

    def delete_selected_account(self):
        sel = self.accounts_listbox.curselection()
        if not sel:
            messagebox.showwarning('Warning','Select an account to delete')
            return
        text = self.accounts_listbox.get(sel[0])
        acct_no = text.split(' ')[0]
        if messagebox.askyesno('Confirm','Delete account %s and all its transactions?'%acct_no):
            self.db.delete_account(acct_no)
            self.refresh_account_list()
            if self.current_account == acct_no:
                self.current_account = None
                self.header_label.config(text='No account selected')
                self.balance_var.set('')
                for i in self.tree.get_children():
                    self.tree.delete(i)

    def login(self):
        acct = self.login_acc_var.get().strip()
        pin = self.login_pin_var.get().strip()
        if not acct or not pin:
            messagebox.showwarning('Login','Enter account and PIN')
            return
        if self.db.authenticate(acct, pin):
            messagebox.showinfo('Login','Login successful')
            self.show_account(acct)
        else:
            messagebox.showerror('Login','Invalid account or PIN')

    def logout(self):
        self.current_account = None
        self.header_label.config(text='No account selected')
        self.balance_var.set('')
        for i in self.tree.get_children():
            self.tree.delete(i)

    def deposit_dialog(self):
        if not self.current_account:
            messagebox.showwarning('Deposit','Select or login to an account')
            return
        amt = simpledialog.askfloat('Deposit','Amount to deposit', minvalue=0.01)
        if amt is None:
            return
        try:
            self.db.deposit(self.current_account, float(amt))
            messagebox.showinfo('Deposit','Deposit successful')
            self.show_account(self.current_account)
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def withdraw_dialog(self):
        if not self.current_account:
            messagebox.showwarning('Withdraw','Select or login to an account')
            return
        amt = simpledialog.askfloat('Withdraw','Amount to withdraw', minvalue=0.01)
        if amt is None:
            return
        try:
            self.db.withdraw(self.current_account, float(amt))
            messagebox.showinfo('Withdraw','Withdraw successful')
            self.show_account(self.current_account)
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def transfer_dialog(self):
        if not self.current_account:
            messagebox.showwarning('Transfer','Select or login to an account')
            return
        to_acc = simpledialog.askstring('Transfer','Destination account number')
        if not to_acc:
            return
        amt = simpledialog.askfloat('Transfer','Amount to transfer', minvalue=0.01)
        if amt is None:
            return
        try:
            self.db.transfer(self.current_account, to_acc.strip(), float(amt))
            messagebox.showinfo('Transfer','Transfer successful')
            self.show_account(self.current_account)
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def view_history(self):
        if not self.current_account:
            return
        for i in self.tree.get_children():
            self.tree.delete(i)
        rows = self.db.get_transactions(self.current_account, limit=1000)
        for r in rows:
            self.tree.insert('', 'end', values=(r['id'], r['type'], f"{r['amount']:.2f}", r['counterparty'] or '', str(r['timestamp']), r['note'] or ''))

    def on_tx_double(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        tx_id = item['values'][0]
        cur = self.db.conn.cursor()
        cur.execute('SELECT * FROM transactions WHERE id=?', (tx_id,))
        row = cur.fetchone()
        if not row:
            return
        # Offer export PDF for this transaction
        if REPORTLAB_AVAILABLE:
            if messagebox.askyesno('Export PDF','Export this transaction as PDF?'):
                path = filedialog.asksaveasfilename(defaultextension='.pdf', filetypes=[('PDF','*.pdf')])
                if path:
                    try:
                        self.db.export_transaction_pdf(row, path)
                        messagebox.showinfo('PDF','Saved')
                    except Exception as e:
                        messagebox.showerror('Error', str(e))
        else:
            messagebox.showinfo('Transaction', f"ID: {row['id']}\nType: {row['type']}\nAmount: {row['amount']}")

    def export_csv_selected(self):
        sel = self.accounts_listbox.curselection()
        if not sel:
            messagebox.showwarning('Export','Select an account to export')
            return
        text = self.accounts_listbox.get(sel[0])
        acct_no = text.split(' ')[0]
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not path:
            return
        try:
            self.db.export_transactions_csv(acct_no, path)
            messagebox.showinfo('Export','CSV exported')
        except Exception as e:
            messagebox.showerror('Error', str(e))

# ----------------- Dialogs -----------------
class CreateAccountDialog(tk.Toplevel):
    def __init__(self, parent, db:DB):
        super().__init__(parent)
        self.db = db
        self.title('Create Account')
        self.geometry('320x220')
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text='Name').pack(pady=(12,0))
        self.name_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.name_var).pack(fill='x', padx=12)
        ttk.Label(self, text='PIN (4-8 digits)').pack(pady=(8,0))
        self.pin_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.pin_var, show='*').pack(fill='x', padx=12)
        ttk.Label(self, text='Initial deposit (optional)').pack(pady=(8,0))
        self.init_var = tk.DoubleVar(value=0.0)
        ttk.Entry(self, textvariable=self.init_var).pack(fill='x', padx=12)

        ttk.Button(self, text='Create', command=self.create).pack(pady=12)

    def create(self):
        name = self.name_var.get().strip()
        pin = self.pin_var.get().strip()
        init = self.init_var.get()
        if not name or not pin:
            messagebox.showwarning('Create','Name and PIN required')
            return
        if not pin.isdigit() or not (4 <= len(pin) <= 8):
            messagebox.showwarning('PIN','PIN must be 4-8 digits')
            return
        acct = self.db.create_account(name, pin, initial_deposit=float(init))
        messagebox.showinfo('Created', f'Account {acct} created. PIN: {pin} (store it)')
        self.destroy()

# ----------------- Main -----------------

def main():
    app = BankingApp()
    app.mainloop()

if __name__ == '__main__':
    main()
