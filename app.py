from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from sqlite3 import IntegrityError
from functools import wraps

app = Flask(__name__)
# IMPORTANT: Use a complex, randomly generated key in production
app.secret_key = "secret_key" 
# NOTE: Please change this line in a production environment!

# ---------------- Database Connection ----------------
def get_db_connection():
    conn = sqlite3.connect('database.db')
    # Enable foreign key enforcement for data integrity
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- Initialize Database ----------------
def init_db():
    conn = get_db_connection()
    
    # 1. Users Table (for managers/admins)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullName TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT, 
            password TEXT NOT NULL
        )
    ''')
    
    # 2. Apartments Table (the main listing content)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS apartments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            bedrooms INTEGER,
            bathrooms INTEGER,
            location TEXT NOT NULL,
            rent REAL
        )
    ''')

    # 3. Tenants Table (new table for tenant management)
    # Added ON DELETE SET NULL to handle cases where an apartment is deleted
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullName TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            apartment_id INTEGER,
            lease_start TEXT,
            FOREIGN KEY (apartment_id) REFERENCES apartments (id) ON DELETE SET NULL
        )
    ''')
    
    # Insert Sample Apartment Data (Only if the table is empty)
    cursor = conn.execute('SELECT COUNT(*) FROM apartments')
    if cursor.fetchone()[0] == 0:
        print("Inserting sample apartment data...")
        sample_apartments = [
            ('Goro Deluxe Apt', 3, 2, 'Goro', 15000.00),
            ('Kazanchis Studio', 1, 1, 'Kazanchis', 8000.00),
            ('Bole Road Family Home', 4, 3, 'Bole', 25000.00)
        ]
        conn.executemany(
            'INSERT INTO apartments (name, bedrooms, bathrooms, location, rent) VALUES (?, ?, ?, ?, ?)',
            sample_apartments
        )
        
        # Insert a sample tenant to demonstrate occupied/available status
        conn.execute('INSERT INTO tenants (fullName, phone, email, apartment_id, lease_start) VALUES (?, ?, ?, ?, ?)',
                      ('Abebe Kebede', '0911223344', 'abebek@example.com', 1, '2024-01-01'))
    
    conn.commit()
    conn.close()

# ---------------- Utility Functions ----------------

def login_required(f):
    """Decorator to check if user is logged in before accessing a route."""
    @wraps(f) # Use functools.wraps for better decorator function handling
    def wrapper(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash("You must be logged in to view this page.", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return wrapper

# ---------------- Core Routes ----------------

@app.route('/')
def home():
    conn = get_db_connection()
    # UPDATED: Fetch ONLY apartments that are not currently assigned to a tenant
    apartments = conn.execute('''
        SELECT a.*
        FROM apartments a
        LEFT JOIN tenants t ON a.id = t.apartment_id
        WHERE t.apartment_id IS NULL
        ORDER BY a.rent DESC
    ''').fetchall()
    conn.close()
    
    return render_template('index.html', apartments=apartments)

# ---------------- User Authentication ----------------

@app.route('/register', methods=['POST'])
def register():
    fullName = request.form['fullName']
    email = request.form['email']
    phone = request.form['phone']
    password = request.form['password']
    
    # BASIC VALIDATION
    if not all([fullName, email, phone, password]):
        flash("All fields are required for registration.", "error")
        return redirect(url_for('home'))

    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (fullName, email, phone, password) VALUES (?, ?, ?, ?)',
                      (fullName, email, phone, hashed_password))
        conn.commit()
        
        flash("Registration successful! Please log in.", "success")
        
    except IntegrityError:
        flash("Registration failed. That email is already in use.", "error")
        
    finally:
        conn.close()
        
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('loginEmail')
    password = request.form.get('loginPassword')

    if not email or not password:
        flash("Please provide both email and password.", "error")
        return redirect(url_for('home'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user and check_password_hash(user['password'], password):
        # Set session variables to log the user in
        session['logged_in'] = True
        session['user_id'] = user['id']
        session['user_name'] = user['fullName']
        
        flash(f"Welcome back, {user['fullName']}!", "success")
        return redirect(url_for('dashboard')) 
    else:
        flash("Invalid email or password", "error")
        return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear() 
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('home'))

# ---------------- Dashboard & Management Routes ----------------

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    
    # 1. Total Apartment Count
    total_apartments = conn.execute('SELECT COUNT(id) FROM apartments').fetchone()[0]
    
    # 2. Total Occupied Units
    # Count how many *unique* apartments currently have a tenant assigned
    occupied_units = conn.execute('SELECT COUNT(DISTINCT apartment_id) FROM tenants WHERE apartment_id IS NOT NULL').fetchone()[0]
    
    # 3. Total Tenant Count (Total people under management)
    total_tenants = conn.execute('SELECT COUNT(id) FROM tenants').fetchone()[0]
    
    conn.close()
    
    # Calculate available units
    available_apartments = total_apartments - occupied_units

    # Pass the metrics to the dashboard template
    return render_template('dashboard.html', 
        user_name=session['user_name'],
        total_apartments=total_apartments,
        available_apartments=available_apartments,
        total_tenants=total_tenants
    )

# --- Apartment Management (CRUD) ---

@app.route('/add_apartment', methods=['GET', 'POST'])
@login_required
def add_apartment():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        
        # 1. Basic Validation
        if not all([name, location, request.form.get('bedrooms'), request.form.get('bathrooms'), request.form.get('rent')]):
            flash("All fields are required.", "error")
            return render_template('add_apartment.html', form_data=request.form)

        # 2. Type/Value Validation
        try:
            bedrooms = int(request.form['bedrooms'])
            bathrooms = int(request.form['bathrooms'])
            rent = float(request.form['rent'])
            
            if bedrooms <= 0 or bathrooms <= 0 or rent <= 0:
                 raise ValueError("Bedrooms, Bathrooms, and Rent must be positive numbers.")

        except ValueError as e:
            flash(f"Data error: {e}", "error")
            return render_template('add_apartment.html', form_data=request.form) # Return submitted data

        conn = get_db_connection()
        conn.execute('INSERT INTO apartments (name, location, bedrooms, bathrooms, rent) VALUES (?, ?, ?, ?, ?)',
                      (name, location, bedrooms, bathrooms, rent))
        conn.commit()
        conn.close()
        
        flash(f"Apartment '{name}' added successfully!", "success")
        return redirect(url_for('manage_apartments'))
        
    return render_template('add_apartment.html')

@app.route('/manage_apartments')
@login_required
def manage_apartments():
    conn = get_db_connection()
    # UPDATED: Join apartments with tenants to determine occupancy status (tenant_count)
    apartments = conn.execute('''
        SELECT 
            a.*,
            COUNT(t.id) AS tenant_count
        FROM 
            apartments a
        LEFT JOIN 
            tenants t ON a.id = t.apartment_id
        GROUP BY
            a.id
        ORDER BY 
            a.name
    ''').fetchall()
    conn.close()
    return render_template('manage_apartments.html', apartments=apartments)

@app.route('/edit_apartment/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_apartment(id):
    conn = get_db_connection()
    # UPDATED: Join with tenants to get current tenant info for display
    apartment = conn.execute('''
        SELECT 
            a.*, 
            t.fullName AS tenant_name, 
            t.id AS tenant_id
        FROM 
            apartments a
        LEFT JOIN 
            tenants t ON a.id = t.apartment_id
        WHERE 
            a.id = ?
    ''', (id,)).fetchone()

    if apartment is None:
        conn.close()
        flash("Apartment not found.", "error")
        return redirect(url_for('manage_apartments'))

    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        
        # Type/Value Validation
        try:
            bedrooms = int(request.form['bedrooms'])
            bathrooms = int(request.form['bathrooms'])
            rent = float(request.form['rent'])
            
            if bedrooms <= 0 or bathrooms <= 0 or rent <= 0:
                 raise ValueError("Bedrooms, Bathrooms, and Rent must be positive numbers.")
        except ValueError as e:
            flash(f"Data error: {e}", "error")
            conn.close()
            # Return GET request to fetch original apartment data again
            return redirect(url_for('edit_apartment', id=id))

        conn.execute('UPDATE apartments SET name = ?, location = ?, bedrooms = ?, bathrooms = ?, rent = ? WHERE id = ?',
                      (name, location, bedrooms, bathrooms, rent, id))
        conn.commit()
        conn.close()
        flash(f"Apartment '{name}' updated successfully!", "success")
        return redirect(url_for('manage_apartments'))

    conn.close()
    return render_template('edit_apartment.html', apartment=apartment)

@app.route('/delete_apartment/<int:id>', methods=['POST'])
@login_required
def delete_apartment(id):
    conn = get_db_connection()
    apartment = conn.execute('SELECT name FROM apartments WHERE id = ?', (id,)).fetchone()
    
    # Deletion is safe due to ON DELETE SET NULL constraint on tenants table
    conn.execute('DELETE FROM apartments WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    if apartment:
        flash(f"Apartment '{apartment['name']}' deleted successfully. Any linked tenants are now unassigned.", "success")
    else:
        flash("Apartment deleted successfully.", "success")
        
    return redirect(url_for('manage_apartments'))

# --- Tenant Management (CRUD) ---

@app.route('/add_tenant', methods=['GET', 'POST'])
@login_required
def add_tenant():
    conn = get_db_connection()
    
    # 1. Get ONLY AVAILABLE apartments for the assignment dropdown
    available_apartments = conn.execute('''
        SELECT a.id, a.name
        FROM apartments a
        LEFT JOIN tenants t ON a.id = t.apartment_id
        WHERE t.apartment_id IS NULL
        ORDER BY a.name
    ''').fetchall()
    
    if request.method == 'POST':
        fullName = request.form.get('fullName')
        phone = request.form.get('phone')
        email = request.form.get('email')
        apartment_id = request.form.get('apartment_id') # Can be 'None' if unassigned
        lease_start = request.form.get('lease_start')

        # --- DEBUGGING: Print received data to console ---
        print(f"--- ADD TENANT DATA RECEIVED ---")
        print(f"Full Name: {fullName}")
        print(f"Phone: {phone}")
        print(f"Email: {email}")
        print(f"Lease Start: {lease_start}")
        print(f"Apartment ID (Raw): {apartment_id}")
        print(f"----------------------------------")
        # -----------------------------------------------

        # Basic Validation
        if not all([fullName, phone, lease_start]):
            flash("Tenant's Full Name, Phone, and Lease Start Date are required.", "error")
            conn.close() # Close connection if returning early
            # Pass back the available apartments list for re-rendering
            return render_template('add_tenant.html', available_apartments=available_apartments, form_data=request.form)

        # Handle unassigned case: convert 'None' string to actual None/NULL
        # If apartment_id is 'None' (from the dropdown) or None (if field was somehow missing), set to None
        # Otherwise, attempt to cast it to an integer
        apt_id_for_db = None
        if apartment_id and apartment_id != 'None':
             try:
                # IMPORTANT: Convert the string ID from the form to an integer for the database
                apt_id_for_db = int(apartment_id) 
             except ValueError:
                 flash("Invalid apartment selection. The apartment ID must be a number.", "error")
                 conn.close()
                 return render_template('add_tenant.html', available_apartments=available_apartments, form_data=request.form)

        try:
            conn.execute('INSERT INTO tenants (fullName, phone, email, apartment_id, lease_start) VALUES (?, ?, ?, ?, ?)',
                         (fullName, phone, email, apt_id_for_db, lease_start))
            conn.commit()
            flash(f"Tenant '{fullName}' added successfully!", "success")
            conn.close() # Close connection on successful completion
            return redirect(url_for('manage_tenants')) 
        except Exception as e:
            # Explicitly flash the error to the user
            flash(f"An unexpected database error occurred while adding the tenant: {e}", "error")
        finally:
            # Ensure connection is closed even if an error occurred
            if conn:
                conn.close()
            
    # GET request handler (or POST returning after exception)
    return render_template('add_tenant.html', available_apartments=available_apartments)


@app.route('/manage_tenants')
@login_required
def manage_tenants():
    """Route to view, edit, and delete all tenant records."""
    conn = get_db_connection()
    
    # Fetch all tenants, joining with the apartments table to show which unit they occupy
    tenants = conn.execute('''
        SELECT 
            t.id, 
            t.fullName, 
            t.phone, 
            t.email, 
            t.lease_start, 
            a.name AS apartment_name
        FROM 
            tenants t
        LEFT JOIN 
            apartments a ON t.apartment_id = a.id
        ORDER BY 
            t.fullName
    ''').fetchall()
    
    conn.close()
    return render_template('manage_tenants.html', tenants=tenants) 

@app.route('/edit_tenant/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_tenant(id):
    conn = get_db_connection()
    
    # 1. Get the current tenant data
    tenant = conn.execute('SELECT * FROM tenants WHERE id = ?', (id,)).fetchone()

    if tenant is None:
        conn.close()
        flash("Tenant not found.", "error")
        return redirect(url_for('manage_tenants'))
    
    # 2. Get available apartments (exclude current tenant's unit unless it's their own)
    available_apartments = conn.execute('''
        SELECT a.id, a.name
        FROM apartments a
        LEFT JOIN tenants t ON a.id = t.apartment_id
        WHERE t.apartment_id IS NULL OR a.id = ?
        ORDER BY a.name
    ''', (tenant['apartment_id'],)).fetchall()

    if request.method == 'POST':
        fullName = request.form.get('fullName')
        phone = request.form.get('phone')
        email = request.form.get('email')
        apartment_id = request.form.get('apartment_id')
        lease_start = request.form.get('lease_start')

        if not all([fullName, phone, lease_start]):
            flash("Tenant's Full Name, Phone, and Lease Start Date are required.", "error")
            conn.close()
            return redirect(url_for('edit_tenant', id=id))

        # Handle unassigned case
        apt_id_for_db = int(apartment_id) if apartment_id and apartment_id != 'None' else None

        try:
            conn.execute('UPDATE tenants SET fullName = ?, phone = ?, email = ?, apartment_id = ?, lease_start = ? WHERE id = ?',
                         (fullName, phone, email, apt_id_for_db, lease_start, id))
            conn.commit()
            flash(f"Tenant '{fullName}' updated successfully!", "success")
            conn.close()
            return redirect(url_for('manage_tenants'))
        except Exception as e:
            flash(f"An error occurred while updating the tenant: {e}", "error")
        finally:
            if conn:
                conn.close()
            
    conn.close()
    return render_template('edit_tenant.html', tenant=tenant, available_apartments=available_apartments)


@app.route('/delete_tenant/<int:id>', methods=['POST'])
@login_required
def delete_tenant(id):
    conn = get_db_connection()
    tenant = conn.execute('SELECT fullName FROM tenants WHERE id = ?', (id,)).fetchone()
    
    if tenant:
        try:
            conn.execute('DELETE FROM tenants WHERE id = ?', (id,))
            conn.commit()
            flash(f"Tenant '{tenant['fullName']}' deleted successfully.", "success")
        except Exception as e:
            flash(f"Error deleting tenant: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Tenant not found.", "error")
        
    return redirect(url_for('manage_tenants'))

# ---------------- Run App ----------------
if __name__ == "__main__":
    init_db()
    print("Starting Rent in Addis Flask server...")
    app.run(debug=True)
