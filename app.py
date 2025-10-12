from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room
from models import db, User, Conversation, Message
import os

app = Flask(__name__)
app.secret_key = "secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# 업로드 폴더 설정 (이미 잘 설정되어 있습니다)
app.config["UPLOAD_FOLDER"] = "static/uploads"

# 폴더 자동 생성 (이미 잘 설정되어 있습니다)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)
socketio = SocketIO(app)

# DB 초기화
with app.app_context():
    # ⚠️ Render는 database.db 파일이 항상 사라지므로,
    #    항상 db.create_all()을 호출하여 테이블 구조를 보장합니다.
    #    데이터가 사라지는 것은 개발 단계의 SQLite 한계입니다.
    db.create_all()
    print("✅ 데이터베이스 테이블 구조 확인 및 생성 완료.")

    if not User.query.filter_by(is_admin=True).first():
        # ... (관리자 계정 생성 로직은 그대로) ...
        admins = [
            # ... (관리자 정보)
        ]
        db.session.add_all(admins)
        db.session.commit()
        print("✅ 관리자 3명 생성 완료 (admin1~3 / 비번 127127)")


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("chat_list"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash("회원가입 완료! 로그인하세요.")
        return redirect(url_for("login"))
    return render_template("register.html")


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


@app.route("/chat_list")
def chat_list():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if user is None:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    if hasattr(user, "is_admin") and user.is_admin:
        conversations = Conversation.query.all()
    else:
        conversations = Conversation.query.filter_by(user_q_id=user.id).all()

    return render_template("chat_list.html", user=user, conversations=conversations)


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


@app.route("/chat/<int:conversation_id>")
def chat(conversation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session["user_id"])

    if not user.is_admin and conversation.user_q_id != user.id:
        flash("접근 권한이 없습니다.")
        return redirect(url_for("chat_list"))

    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.timestamp.asc()).all()
    return render_template("chat.html", conversation=conversation, messages=messages, user=user)


# 기존 이미지 업로드 라우트 (채팅용)
@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return {"error": "파일이 없습니다."}, 400

    file = request.files["image"]
    if file.filename == "":
        return {"error": "파일 이름이 없습니다."}, 400

    filename = secure_filename(file.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    return {"image_url": f"/{path}"}


# Socket.IO 이벤트
@socketio.on("send_message")
def handle_send_message(data):
    conversation_id = data["conversation_id"]
    user_id = data["user_id"]
    content = data.get("content", "").strip()
    image_url = data.get("image_url", None)

    if not content and not image_url:
        return

    msg = Message(conversation_id=conversation_id, sender_id=user_id, content=content, image_path=image_url)
    db.session.add(msg)
    db.session.commit()

    emit("receive_message", {
        "sender_id": user_id,
        "content": content,
        "image_url": image_url
    }, room=f"room_{conversation_id}")


@socketio.on("join")
def on_join(data):
    room = f"room_{data['conversation_id']}"
    join_room(room)
    print(f"✅ 사용자가 {room} 방에 참여했습니다.")

# -------------------- 👇 ChatGPT가 알려준 기능 추가된 부분 👇 --------------------

# 1. 사진 목록을 보여주고, 업로드 폼을 제공하는 페이지
@app.route('/upload_test')
def upload_test():
    # static/uploads 폴더에 있는 파일 목록을 가져옴
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    # upload_test.html 템플릿을 렌더링하며 파일 목록을 전달
    return render_template('upload_test.html', files=files)

# 2. 파일 업로드를 처리하는 라우트
@app.route('/upload_action', methods=['POST'])
def upload_action():
    if 'file' not in request.files:
        flash('파일이 선택되지 않았습니다.')
        return redirect(url_for('upload_test'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('선택된 파일이 없습니다.')
        return redirect(url_for('upload_test'))
    
    if file:
        # werkzeug의 secure_filename을 사용하여 안전한 파일 이름으로 변경
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        flash(f'"{filename}" 파일이 성공적으로 업로드되었습니다!')
        return redirect(url_for('upload_test'))

# -------------------- 👆 여기까지 추가 👆 --------------------

# app.py 파일 하단 (wsgi.py를 위해 이 코드는 이제 사용되지 않음)

if __name__ == "__main__":
    # with app.app_context(): # <-- 이 부분을 이제 지우거나 주석 처리
    #     db.create_all()     # <-- 이 부분을 이제 지우거나 주석 처리
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)