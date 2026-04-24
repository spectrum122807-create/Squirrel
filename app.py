from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'FEHJGEKYGFEFNEWH ASJBKFKBS'
socketio = SocketIO(app)
print("Current Working Directory:", os.getcwd())
def cleanup_old_listings():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        DELETE FROM listings
        WHERE created_at <= datetime('now', '-440 minutes')
        OR status = 'closed'
    """)
    # delete old requests
    c.execute("""
        DELETE FROM requests
        WHERE created_at <= datetime('now', '-440 minutes')
        OR status = 'closed'
    """)
    
    # delete old notifications (keep agreed/declined ones a bit longer)
    c.execute("""
        DELETE FROM notifications
        WHERE created_at <= datetime('now', '-40 minutes')
        AND message NOT LIKE '%Agreed%'
        AND message NOT LIKE '%Declined%'
    """)
    
    # delete agreed/declined notifications after 2 hours
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
            return redirect(url_for("dashboard"))
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
        return redirect(url_for("dashboard"))
    return render_template("signup.html")
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    cleanup_old_listings()  # add this line
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

    if row:
        room_number = row[0]
        
    else:
        room_number = None 

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
    return render_template("dashboard.html",
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
    # delete any previous notification first to avoid duplicates
    c.execute("""
        DELETE FROM notifications
        WHERE user_id=? AND message LIKE ?
    """, (owner_id, f"%{session['user']}%interested%{listing_title}%"))
    # insert fresh notification
    c.execute("""
        INSERT INTO notifications (user_id, message)
        VALUES (?, ?)
    """, (owner_id,
          f"{session['user']} (Room {room}) is interested in your listing '{listing_title}'"))
    conn.commit()
        
    conn.close()
    return redirect(url_for("dashboard"))

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
        return redirect(url_for("request_page"))  # <-- inside POST block

    # GET logic below
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
        UPDATE notifications SET is_read=1
        WHERE user_id=(SELECT id FROM users WHERE username=?)
        AND message LIKE '%do you have it%'
    """, (session["user"],))
    conn.commit()
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
@app.route("/have/<int:request_id>")
def have(request_id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT id, room_number FROM users WHERE username=?", (session["user"],))
    seller = c.fetchone()
    seller_id = seller[0]
    room = seller[1] if seller[1] else "not set"

    c.execute("SELECT id FROM availabilities WHERE request_id=? AND seller_id=?",
              (request_id, seller_id))
    existing = c.fetchone()

    if not existing:
        c.execute("INSERT INTO availabilities (request_id, seller_id) VALUES (?, ?)",
                  (request_id, seller_id))

        # Fetch the request details
        c.execute("SELECT user_id, title FROM requests WHERE id=?", (request_id,))
        req = c.fetchone()

    if req:
        owner_id = req[0]
    request_title = req[1]
    # delete previous notification first
    c.execute("""
        DELETE FROM notifications
        WHERE user_id=? AND message LIKE ?
    """, (owner_id, f"%{session['user']}%{request_title}%available%"))
    # insert fresh
    c.execute("""
        INSERT INTO notifications (user_id, message)
        VALUES (?, ?)
    """, (owner_id,
          f"{session['user']} (Room {room}) has '{request_title}' available for you"))
    conn.commit()

    conn.close()
    return redirect(url_for("request_page"))
@app.route("/delete_request/<int:id>")
def delete_request(id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        DELETE FROM requests
        WHERE id=? AND user_id=(SELECT id FROM users WHERE username=?)
    """, (id, session["user"]))
    conn.commit()
    conn.close()
    return redirect(url_for("request_page"))

@app.route("/notifications")
def notifications():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    user_id = c.fetchone()[0]
    c.execute("""
        SELECT id, message, is_read, created_at
        FROM notifications
        WHERE user_id=?
        ORDER BY created_at DESC
    """, (user_id,))
    notifs = c.fetchall()
   
    c.execute("""
    UPDATE notifications SET is_read=1
    WHERE user_id=? 
      AND (
        message NOT LIKE '%interested%'
        OR message LIKE '%✓ Agreed%'
    )
""", (user_id,))
    c.execute("""
    DELETE FROM notifications
    WHERE created_at <= datetime('now', '-50 minutes')
    AND message NOT LIKE '%interested%'
    OR (
        message LIKE '%✓ Agreed%'
        AND created_at <= datetime('now', '-50 minutes')
    )
""")
    c.execute("""
    SELECT COUNT(*) FROM messages
    WHERE receiver=? AND is_read=0
""", (session["user"],))
    chat_notif_count = c.fetchone()[0]
    conn.commit()
    conn.close()
    return render_template("notifications.html",
                           username=session["user"],
                           notifs=notifs,
                            chat_notif_count=chat_notif_count)
@app.route("/agree/<int:notif_id>")
def agree(notif_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT * FROM notifications WHERE id=?", (notif_id,))
    notif = c.fetchone()

    if notif:
        message = notif[2]
        buyer_username = message.split(" ")[0]

        c.execute("SELECT id, room_number FROM users WHERE username=?", (buyer_username,))
        buyer = c.fetchone()

        if buyer:
            buyer_id = buyer[0]
            buyer_room = buyer[1] if buyer[1] else "not set"

            c.execute("SELECT id, room_number FROM users WHERE username=?", (session["user"],))
            seller = c.fetchone()
            seller_id = seller[0]
            seller_room = seller[1] if seller[1] else "not set"

            try:
                listing_title = message.split("'")[1]
            except:
                listing_title = "the item"

            # mark listing as closed
            c.execute("""
                UPDATE listings SET status='closed'
                WHERE title=? AND user_id=?
            """, (listing_title, seller_id))
            # delete chat between buyer and seller
            c.execute("""
                DELETE FROM messages
                WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
            """, (buyer_username, session["user"], session["user"], buyer_username))
            # find all other interested buyers
            c.execute("""
                SELECT interests.buyer_id
                FROM interests
                JOIN listings ON interests.listing_id = listings.id
                WHERE listings.title=?
                AND listings.user_id=?
                AND interests.buyer_id != ?
            """, (listing_title, seller_id, buyer_id))
            other_buyers = c.fetchall()

            # notify each declined buyer
            for other_buyer in other_buyers:
                other_buyer_id = other_buyer[0]
                c.execute("""
                    INSERT INTO notifications (user_id, message)
                    VALUES (?, ?)
                """, (other_buyer_id,
                      f"Sorry, '{listing_title}' has been sold to someone else"))

            # mark other interest notifications as declined
            c.execute("""
                UPDATE notifications
                SET message = message || ' ✓ Declined',
                    is_read = 1
                WHERE user_id=?
                AND message LIKE ?
                AND message NOT LIKE '%✓ Agreed%'
                AND message NOT LIKE '%✓ Declined%'
            """, (seller_id, f"%interested%{listing_title}%"))

            # notify buyer
            c.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (buyer_id,
                  f"{session['user']} agreed to sell '{listing_title}' to you! Find them at Room {seller_room}"))

            # notify seller
            c.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (seller_id,
                  f"You agreed to sell '{listing_title}' to {buyer_username} (Room {buyer_room}). Exchange confirmed!"))

            # mark original as agreed
            c.execute("""
                UPDATE notifications SET message = message || ' ✓ Agreed'
                WHERE id=?
            """, (notif_id,))

            conn.commit()

    conn.close()
    return redirect(url_for("notifications"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return render_template("login.html")


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
    
    # Return JSON for real-time fetch calls
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
    
    # Return full page for direct URL access
    return render_template("dashboard.html",
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
        return redirect(url_for("dashboard"))
    
    # Load chat history
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

@socketio.on("send_message")
def handle_message(data):
    sender = session["user"]
    receiver = data["receiver"]
    message = data["message"].strip()
    if not message:
        return
    
    # Save to DB
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO messages (sender, receiver, message)
        VALUES (?, ?, ?)
    """, (sender, receiver, message))
    conn.commit()
    conn.close()

    # Create a consistent room name for the two users
    room = "_".join(sorted([sender, receiver]))
    emit("receive_message", {
        "sender": sender,
        "message": message
    }, room=room)

@socketio.on("join")
def on_join(data):
    sender = session["user"]
    receiver = data["receiver"]
    room = "_".join(sorted([sender, receiver]))
    join_room(room)
    
@app.route("/inbox")
def inbox():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    # Get all unique conversations for this user
    c.execute("""
        SELECT DISTINCT
            CASE WHEN sender=? THEN receiver ELSE sender END as other_user,
            MAX(timestamp) as last_time,
            (SELECT message FROM messages m2 
             WHERE (m2.sender=? AND m2.receiver=other_user) 
             OR (m2.sender=other_user AND m2.receiver=?)
             ORDER BY m2.timestamp DESC LIMIT 1) as last_msg
        FROM messages
        WHERE sender=? OR receiver=?
        GROUP BY other_user
        ORDER BY last_time DESC
    """, (session["user"], session["user"], session["user"], session["user"], session["user"]))
    conversations = c.fetchall()
    c.execute("""
    UPDATE messages SET is_read=1
    WHERE receiver=? AND sender=?
""", (sender, receiver))
    conn.commit()
    conn.close()
    return render_template("inbox.html",
                           username=session["user"],
                           conversations=conversations)
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
    # get listing title to delete notification
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
    return redirect(url_for("dashboard"))
@app.route("/unhave/<int:request_id>")
def unhave(request_id):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    seller_id = c.fetchone()[0]
    c.execute("DELETE FROM availabilities WHERE request_id=? AND seller_id=?",
              (request_id, seller_id))
    # delete the notification
    c.execute("SELECT user_id, title FROM requests WHERE id=?", (request_id,))
    req = c.fetchone()
    if req:
        owner_id = req[0]
        request_title = req[1]
        c.execute("""
            DELETE FROM notifications
            WHERE user_id=? AND message LIKE ?
        """, (owner_id, f"%{session['user']}%{request_title}%available%"))
    conn.commit()
    conn.close()
    return redirect(url_for("request_page"))





# delete user data---
# import sqlite3
# conn = sqlite3.connect("users.db")
# c = conn.cursor()
# c.execute("DELETE FROM users")
# conn.commit()
# conn.close()
if __name__ == "__main__":
  socketio.run(app, debug=True)