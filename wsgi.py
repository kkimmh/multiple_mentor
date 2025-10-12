# wsgi.py 파일 시작

# 1. eventlet 라이브러리를 먼저 불러옵니다.
import eventlet

# 2. 모든 다른 모듈을 import 하기 전에 파이썬 기본 기능을 eventlet 환경에 맞게 조정(패치)합니다.
#    이것이 오류를 해결하는 핵심 단계입니다!
eventlet.monkey_patch()

# 3. 이제 app.py에 정의된 실제 Flask 앱과 SocketIO 객체를 안전하게 불러옵니다.
from app import app, socketio

# 4. Gunicorn이 실행할 수 있도록 Flask 앱 인스턴스(app)를 제공합니다.
#    Gunicorn은 이 파일을 실행하고, 이 'app' 변수에 접근하여 웹 서버를 시작합니다.
if __name__ == '__main__':
    # 로컬에서 테스트할 때는 이 코드를 통해 socketio.run()으로 실행됩니다.
    socketio.run(app)

# wsgi.py 파일 끝