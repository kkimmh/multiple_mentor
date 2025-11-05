from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room
from models import db, User, Conversation, Message
import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-secret-key")

# -------------------- 🧠 DB 연결 --------------------
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    print("✅ Render PostgreSQL 사용 중")
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///local.db"
    print("✅ 로컬 SQLite(local.db) 사용 중")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# -------------------- ☁️ Cloudinary 설정 --------------------
cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
api_key = os.environ.get("CLOUDINARY_API_KEY")
api_secret = os.environ.get("CLOUDINARY_API_SECRET")

if cloud_name and api_key and api_secret:
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret
    )
    print("✅ Cloudinary 설정 완료")
else:
    print("⚠️ Cloudinary 환경변수가 설정되지 않았습니다. (이미지 업로드 불가)")

# ------------------------------------------------------------

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------- 📦 DB 초기화 --------------------
with app.app_context():
    db.create_all()
    print("✅ DB 테이블 확인 완료!")

    if not User.query.filter_by(is_admin=True).first():
        admins = [
            User(username="admin1", password=generate_password_hash("127127"), is_admin=True),
            User(username="admin2", password=generate_password_hash("127127"), is_admin=True),
            User(username="admin3", password=generate_password_hash("127127"), is_admin=True)
        ]
        db.session.add_all(admins)
        db.session.commit()
        print("✅ 관리자 3명 생성 완료 (admin1~3 / 비번 127127)")

# ------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("chat_list"))
    return redirect(url_for("login"))

# -------------------- 회원가입 --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))

        db.session.add(User(username=username, password=password))
        db.session.commit()
        flash("회원가입 완료! 로그인하세요.")
        return redirect(url_for("login"))
    return render_template("register.html")

# -------------------- 로그인 --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password, password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash(f"환영합니다, {user.username}님!")
        return redirect(url_for("chat_list"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("login"))

# -------------------- 채팅방 목록 --------------------
@app.route("/chat_list")
def chat_list():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    if user.is_admin:
        conversations = Conversation.query.all()
    else:
        conversations = Conversation.query.filter_by(user_q_id=user.id).all()

    return render_template("chat_list.html", user=user, conversations=conversations)

# -------------------- 채팅방 생성 --------------------
@app.route("/create_conversation", methods=["GET", "POST"])
def create_conversation():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_q_id = session["user_id"]

    if request.method == "POST":
        title = request.form["title"]
        admin = User.query.filter_by(is_admin=True).first()

        if not admin:
            flash("어드민 계정이 없습니다!")
            return redirect(url_for("chat_list"))

        new_conversation = Conversation(title=title, user_q_id=user_q_id, user_a_id=admin.id)
        db.session.add(new_conversation)
        db.session.commit()
        flash("대화방이 생성되었습니다!")
        return redirect(url_for("chat_list"))
    return render_template("create_conversation.html")

# -------------------- 채팅방 내용 --------------------
@app.route("/chat/<int:conversation_id>")
def chat(conversation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session["user_id"])

    if not user.is_admin and conversation.user_q_id != user.id:
        flash("접근 권한이 없습니다.")
        return redirect(url_for("chat_list"))

    messages = Message.query.filter_by(conversation_id=conversation.id) \
        .join(User, Message.sender_id == User.id) \
        .add_columns(User.username.label('sender_username'),
                     Message.content,
                     Message.image_path,
                     Message.timestamp) \
        .order_by(Message.timestamp.asc()).all()

    return render_template("chat.html", conversation=conversation, messages=messages, user=user)

# -------------------- 이미지 업로드 --------------------
@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "파일 이름이 없습니다."}), 400

    try:
        if not (cloud_name and api_key and api_secret):
            raise ValueError("Cloudinary 설정이 없습니다.")
        upload_result = cloudinary.uploader.upload(file)
        image_url = upload_result["secure_url"]
        return jsonify({"image_url": image_url})
    except Exception as e:
        print(f"❌ Cloudinary 업로드 오류: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------- 실시간 메시지 --------------------
@socketio.on("send_message")
def handle_send_message(data):
    conversation_id = data["conversation_id"]
    user_id = data["user_id"]
    content = data.get("content", "").strip()
    image_url = data.get("image_url", None)

    if not content and not image_url:
        return

    msg = Message(conversation_id=conversation_id,
                  sender_id=user_id,
                  content=content,
                  image_path=image_url)
    db.session.add(msg)
    db.session.commit()

    sender = User.query.get(user_id)
    sender_username = sender.username if sender else "알 수 없음"

    emit("receive_message", {
        "sender_id": user_id,
        "sender_username": sender_username,
        "content": content,
        "image_url": image_url
    }, room=f"room_{conversation_id}")

@socketio.on("join")
def on_join(data):
    room = f"room_{data['conversation_id']}"
    join_room(room)
    print(f"✅ {room} 방 참여 완료")

# -------------------- 대화방 삭제 --------------------
@app.route("/delete_conversation/<int:conversation_id>")
def delete_conversation(conversation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    conversation = Conversation.query.get_or_404(conversation_id)

    if not user.is_admin:
        flash("채팅방을 삭제할 권한이 없습니다.")
        return redirect(url_for("chat_list"))

    Message.query.filter_by(conversation_id=conversation_id).delete()
    db.session.delete(conversation)
    db.session.commit()

    flash(f"'{conversation.title}' 대화방이 삭제되었습니다.")
    return redirect(url_for("chat_list"))

# ------------------------------------------------------------
if __name__ == "__main__":
    from waitress import serve
    import os
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)

