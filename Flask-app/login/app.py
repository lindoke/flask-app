from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
import subprocess
from werkzeug.utils import secure_filename
import os
import zipfile
from datetime import datetime

 
app = Flask(__name__)
app.debug = True
 
app.secret_key = 'key'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'root'
app.config['MYSQL_DB'] = 'web-app'
app.config['UPLOAD_FOLDER']='static\\uploads'
 
mysql = MySQL(app)
 
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/login', methods =['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM accounts WHERE username = % s AND password = % s', (username, password, ))
        account = cursor.fetchone()
        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            session['role'] = account['role']
            msg = 'Logged in successfully !'
            return render_template('index.html', msg = msg)
        else:
            msg = 'Incorrect username / password !'
    return render_template('login.html', msg = msg)
 
@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'loggedin' in session and 'role' in session and session['role'] == 'superadmin':
        if request.method == 'POST':
            command = request.form['command']
            try:
                output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, universal_newlines=True)
            except subprocess.CalledProcessError as e:
                output = f"Error: {e.output}"
            return render_template('admin.html', output=output)
        else:
            return render_template('admin.html', output=None)
    else:
        return redirect(url_for('login'))
    
@app.route('/create_share', methods=['GET', 'POST'])
def create_share():
    if 'loggedin' in session:
        if request.method == 'POST':
            # Get share name from the form
            share_name = request.form['share_name']

            # Check if share with this name already exists
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('SELECT * FROM shares WHERE share_name = %s', (share_name,))
            existing_share = cursor.fetchone()
            if existing_share:
                flash('Share with this name already exists', 'error')
                return redirect(request.url)

            # Continue with the share creation process if share with this name doesn't exist
            if 'file' not in request.files:
                flash('No file part', 'error')
                return redirect(request.url)
            file = request.files['file']
            if file.filename == '':
                flash('No selected file', 'error')
                return redirect(request.url)
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                # Get the user's ID from the session
                user_id = session['id']

                # Insert data into the shares table with the owner's ID
                cursor.execute('INSERT INTO shares (share_name, owner_id) VALUES (%s, %s)', (share_name, user_id))
                share_id = cursor.lastrowid
                
                # Insert data into the files table
                cursor.execute('INSERT INTO files (file_name, share_id) VALUES (%s, %s)', (filename, share_id))
                mysql.connection.commit()
                
                flash('Share created successfully', 'success')
                return redirect(url_for('index'))  # Redirect to the index page after successful share creation
        return render_template('create_share.html')
    else:
        return redirect(url_for('login'))

    
@app.route('/download_share/<int:share_id>', methods=['GET'])
def download_share(share_id):
    if 'loggedin' in session:
        # Fetch files within the specified share
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT file_name FROM files WHERE share_id = %s', (share_id,))
        files = cursor.fetchall()
        
        # Fetch share name
        cursor.execute('SELECT share_name FROM shares WHERE id = %s', (share_id,))
        share_name = cursor.fetchone()['share_name']
        
        # Create a temporary directory to store files
        temp_dir = 'static/uploads/tmp'
        os.makedirs(temp_dir, exist_ok=True)
        
        # Add each file to the zip archive
        zip_path = os.path.join(temp_dir, f'share_{share_name}.zip')
        with zipfile.ZipFile(zip_path, 'w') as zip_file:
            for file in files:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file['file_name'])
                zip_file.write(file_path, os.path.join(share_name, os.path.basename(file_path)))
        
        # Send the zip file to the user for download
        return send_file(zip_path, as_attachment=True)
    else:
        return redirect(url_for('login'))


@app.route('/add_comment/<int:share_id>', methods=['POST'])
def add_comment(share_id):
    if 'loggedin' in session:
        if request.method == 'POST':
            # Get user_id from session
            user_id = session['id']
            # Get comment from form
            comment = request.form['comment']
            # Get current timestamp
            created_at = datetime.now()
            
            # Insert comment into database
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('INSERT INTO comments (share_id, user_id, comment, created_at) VALUES (%s, %s, %s, %s)', 
                           (share_id, user_id, comment, created_at))
            mysql.connection.commit()
            flash('Comment added successfully', 'success')
            return redirect(url_for('file_shares'))
    else:
        return redirect(url_for('login'))

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    if 'loggedin' in session:
        if request.method == 'POST':
            # Delete comment from database
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('DELETE FROM comments WHERE id = %s', (comment_id,))
            mysql.connection.commit()
            flash('Comment deleted successfully', 'success')
            return redirect(url_for('file_shares'))
    else:
        return redirect(url_for('login'))

@app.route('/file_shares')
def file_shares():
    if 'loggedin' in session:
        # Initialize lists for shares, files, and comments
        shares = []
        files = []
        comments = []

        # Fetch all file shares owned by the current user
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        user_id = session['id']
        cursor.execute('SELECT * FROM shares WHERE owner_id = %s', (user_id,))
        shares = cursor.fetchall()
        
        for share in shares:
            # Fetch files within each share
            cursor.execute('SELECT * FROM files WHERE share_id = %s', (share['id'],))
            files.extend(cursor.fetchall())
            
            # Fetch comments for each share
            cursor.execute('SELECT * FROM comments WHERE share_id = %s', (share['id'],))
            comments.extend(cursor.fetchall())
        
        return render_template('file_shares.html', shares=shares, files=files, comments=comments)
    else:
        return redirect(url_for('login'))


@app.route('/register', methods =['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form :
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM accounts WHERE username = % s', (username, ))
        account = cursor.fetchone()
        if account:
            msg = 'Account already exists !'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address !'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers !'
        elif not username or not password or not email:
            msg = 'Please fill out the form !'
        else:
            cursor.execute('INSERT INTO accounts VALUES (NULL, % s, % s, % s, role)', (username, password, email, ))
            mysql.connection.commit()
            msg = 'You have successfully registered !'
    elif request.method == 'POST':
        msg = 'Please fill out the form !'
    return render_template('register.html', msg = msg)


@app.route('/routes', methods =['GET', 'POST'])
def get_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': ','.join(rule.methods),
            'path': str(rule),
        })
    return routes

# Print all registered routes
print(get_routes())