from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'FEHJGEKYGFEFNEWH ASJBKFKBS'
socketio = SocketIO(app)

def cleanup_old_listings():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        DELETE FROM listings
        WHERE created_at <= datetime('now', '-440 minutes')
        OR status = 'closed'
    """)
    c.execute("""
        DELETE FROM requests
        WHERE created_at <= datetime('now', '-440 minutes')
        OR status = 'closed'
    """)
    c.execute("""
        DELETE FROM notifications
        WHERE created_at <= datetime('now', '-40 minutes')
        AND message NOT LIKE '%Agreed%'
        AND message NOT LIKE '%Declined%'
    """)
    c.execute("""
        DELETE FROM notifications
        WHERE created_at <= datetime('now', '-120 minutes')
    """)
    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
       
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user"] = username
            return redirect(url_for("index")) # Updated to index
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        room_number = request.form.get("room_number")
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        existing_user = c.fetchone()
        if existing_user:
            conn.close()
            return render_template("signup.html", error="Account already exists!!!")
        c.execute("INSERT INTO users (username, password, room_number) VALUES (?, ?, ?)",
                  (username, password, room_number))
        conn.commit()
        conn.close()
        session["user"] = username
        return redirect(url_for("index")) # Updated to index
    return render_template("signup.html")

@app.route("/dashboard")
def index(): # Renamed function to index
    if "user" not in session:
        return redirect(url_for("login"))
    cleanup_old_listings()
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        SELECT listings.id, listings.title, listings.price,
               listings.description, users.username, listings.status
        FROM listings
        JOIN users ON listings.user_id = users.id
        ORDER BY listings.created_at DESC
        LIMIT 10
    """)
    listings = c.fetchall()

    c.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id=(SELECT id FROM users WHERE username=?)
        AND is_read=0
        AND message NOT LIKE '%✓ Agreed%'
        AND message NOT LIKE '%do you have it%'      
    """, (session["user"],))
    notif_count = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM messages
        WHERE receiver=? AND is_read=0
    """, (session["user"],))
    chat_notif_count = c.fetchone()[0]
    
    c.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id=(SELECT id FROM users WHERE username=?)
        AND is_read=0
        AND message LIKE '%do you have it%'
    """, (session["user"],))
    request_notif_count = c.fetchone()[0]

    c.execute("SELECT room_number FROM users WHERE username=?", (session["user"],))
    row = c.fetchone()
    room_number = row[0] if row else None

    c.execute("""
        SELECT COUNT(*) FROM listings
        WHERE user_id=(SELECT id FROM users WHERE username=?)
    """, (session["user"],))
    listing_count = c.fetchone()[0]
    
    c.execute("""
        SELECT listing_id FROM interests
        WHERE buyer_id=(SELECT id FROM users WHERE username=?)
    """, (session["user"],))
    user_interests = [row[0] for row in c.fetchall()]
    conn.close()
    
    return render_template("index.html", # Updated template name
                           username=session["user"],
                           listings=listings,
                           notif_count=notif_count,
                           request_notif_count=request_notif_count,
                           room_number=room_number,
                           listing_count=listing_count,
                           chat_notif_count=chat_notif_count,
                           user_interests=user_interests)

@app.route("/want/<int:listing_id>")
def want(listing_id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id, room_number FROM users WHERE username=?", (session["user"],))
    buyer = c.fetchone()
    buyer_id = buyer[0]
    room = buyer[1] if buyer[1] else "not set"
    c.execute("SELECT id FROM interests WHERE listing_id=? AND buyer_id=?",
              (listing_id, buyer_id))
    existing = c.fetchone()
    if not existing:
        c.execute("INSERT INTO interests (listing_id, buyer_id) VALUES (?, ?)",
                  (listing_id, buyer_id))
    c.execute("SELECT user_id, title FROM listings WHERE id=?", (listing_id,))
    listing = c.fetchone()
    owner_id = listing[0]
    listing_title = listing[1]
    c.execute("""
        DELETE FROM notifications
        WHERE user_id=? AND message LIKE ?
    """, (owner_id, f"%{session['user']}%interested%{listing_title}%"))
    c.execute("""
        INSERT INTO notifications (user_id, message)
        VALUES (?, ?)
    """, (owner_id,
          f"{session['user']} (Room {room}) is interested in your listing '{listing_title}'"))
    conn.commit()
    conn.close()
    return redirect(url_for("index")) # Updated to index

@app.route("/enlist", methods=["GET", "POST"])
def enlist():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    current_user = c.fetchone()
    user_id = current_user[0]
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        price = request.form.get("price")
        c.execute("""
            INSERT INTO listings (user_id, title, description, price)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, description, price))
        conn.commit()
        conn.close()
        return redirect(url_for("enlist"))
    c.execute("""
        SELECT listings.id, listings.title, listings.description,
               listings.price, users.username, listings.created_at
        FROM listings
        JOIN users ON listings.user_id = users.id
        WHERE listings.status = 'open'
        AND listings.user_id = ?
        ORDER BY listings.created_at DESC
    """, (user_id,))
    all_listings = c.fetchall()
    conn.close()
    return render_template("enlist.html",
                           username=session["user"],
                           all_listings=all_listings)

@app.route("/delete_listing/<int:id>")
def delete_listing(id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        DELETE FROM listings
        WHERE id=? AND user_id=(SELECT id FROM users WHERE username=?)
    """, (id, session["user"]))
    conn.commit()
    conn.close()
    return redirect(url_for("enlist"))

@app.route("/request", methods=["GET", "POST"])
def request_page():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        budget = request.form.get("budget")

        c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
        user = c.fetchone()
        user_id = user[0]

        c.execute("""
            INSERT INTO requests (user_id, title, description, budget)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, description, budget))

        c.execute("SELECT id FROM users WHERE id != ?", (user_id,))
        other_users = c.fetchall()
        
        for other_user in other_users:
            c.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (other_user[0],
                  f"{session['user']} is looking for '{title}' — do you have it?"))

        conn.commit()
        conn.close()
        return redirect(url_for("request_page"))

    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    current_user = c.fetchone()
    user_id = current_user[0]
    c.execute("""
        UPDATE notifications SET is_read=1
        WHERE user_id=?
        AND message LIKE '%do you have it%'
    """, (user_id,))
    conn.commit()
    c.execute("""
        SELECT requests.id, requests.title, requests.description,
               requests.budget, users.username, requests.created_at
        FROM requests
        JOIN users ON requests.user_id = users.id
        WHERE requests.status = 'open' AND requests.user_id = ?
        ORDER BY requests.created_at DESC
    """, (user_id,))
    my_requests = c.fetchall()

    c.execute("""
        SELECT requests.id, requests.title, requests.description,
               requests.budget, users.username, requests.created_at
        FROM requests
        JOIN users ON requests.user_id = users.id
        WHERE requests.status = 'open' AND requests.user_id != ?
        ORDER BY requests.created_at DESC
    """, (user_id,))
    other_requests = c.fetchall()

    c.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id=(SELECT id FROM users WHERE username=?)
        AND is_read=0
        AND message NOT LIKE '%✓ Agreed%'
        AND message NOT LIKE '%do you have it%'
    """, (session["user"],))
    notif_count = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id=(SELECT id FROM users WHERE username=?)
        AND is_read=0
        AND message LIKE '%do you have it%'
    """, (session["user"],))
    request_notif_count = c.fetchone()[0]

    c.execute("""
        SELECT request_id FROM availabilities
        WHERE seller_id=(SELECT id FROM users WHERE username=?)
    """, (session["user"],))
    user_availabilities = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template("request.html",
                           username=session["user"],
                           my_requests=my_requests,
                           other_requests=other_requests,
                           notif_count=notif_count,
                           request_notif_count=request_notif_count,
                           user_availabilities=user_availabilities)

@app.route("/search")
def search():
    if "user" not in session:
        return redirect(url_for("login"))
    
    query = request.args.get("q", "").strip()
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    
    if query:
        search_term = f"%{query}%"
        c.execute("""
            SELECT listings.id, listings.title, listings.price,
                   listings.description, users.username, listings.status
            FROM listings
            JOIN users ON listings.user_id = users.id
            WHERE (listings.title LIKE ? OR listings.description LIKE ?)
            ORDER BY listings.created_at DESC
        """, (search_term, search_term))
    else:
        c.execute("""
            SELECT listings.id, listings.title, listings.price,
                   listings.description, users.username, listings.status
            FROM listings
            JOIN users ON listings.user_id = users.id
            ORDER BY listings.created_at DESC
            LIMIT 10
        """)
    
    results = c.fetchall()
    conn.close()
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {"results": [
            {
                "id": r[0],
                "title": r[1],
                "price": r[2],
                "description": r[3],
                "username": r[4],
                "status": r[5]
            } for r in results
        ]}
    
    return render_template("index.html", # Updated template name
                           username=session["user"],
                           listings=results,
                           notif_count=0,
                           search_query=query)

@app.route("/chat/<receiver>")
def chat(receiver):
    if "user" not in session:
        return redirect(url_for("login"))
    sender = session["user"]
    if sender == receiver:
        return redirect(url_for("index")) # Updated to index
    
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        SELECT sender, message, timestamp FROM messages
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        ORDER BY timestamp ASC
    """, (sender, receiver, receiver, sender))
    messages = c.fetchall()
    conn.close()
    return render_template("chat.html",
                           username=sender,
                           receiver=receiver,
                           messages=messages)

@app.route("/unwant/<int:listing_id>")
def unwant(listing_id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    buyer_id = c.fetchone()[0]
    c.execute("DELETE FROM interests WHERE listing_id=? AND buyer_id=?",
              (listing_id, buyer_id))
    c.execute("SELECT user_id, title FROM listings WHERE id=?", (listing_id,))
    listing = c.fetchone()
    if listing:
        owner_id = listing[0]
        listing_title = listing[1]
        c.execute("""
            DELETE FROM notifications
            WHERE user_id=? AND message LIKE ?
        """, (owner_id, f"%{session['user']}%interested%{listing_title}%"))
    conn.commit()
    conn.close()
    return redirect(url_for("index")) # Updated to index

# Note: Keeping original code for other functions (agree, have, etc.) to keep response concise
# Ensure all other functions in your app.py that redirect to "dashboard" are updated to "index"

if __name__ == "__main__":
    socketio.run(app, debug=True)
