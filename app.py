import cv2
import sqlite3
import time
import os
import sys
from threading import Lock
from datetime import datetime
from flask import Flask, render_template, Response, redirect, url_for, request, flash, abort, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np

# 判断打包环境并设置模板路径
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
else:
    template_folder = 'templates'

# 初始化 Flask 应用
app = Flask(__name__, template_folder=template_folder)
app.secret_key = 'your_very_strong_secret_key_here'
app.config['ADMIN_CREDENTIALS'] = {
    'username': 'youzijiang',
    'password': generate_password_hash('20060209czh')
}
csrf = CSRFProtect(app)

# 数据库路径处理
def get_db_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'users.db')
    return 'users.db'

# 初始化数据库
def init_db():
    try:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY,
                      username TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      is_admin BOOLEAN DEFAULT FALSE)''')

        c.execute('''CREATE TABLE IF NOT EXISTS invite_codes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      code TEXT UNIQUE NOT NULL)''')

        c.execute('''CREATE TABLE IF NOT EXISTS video_settings
                     (id INTEGER PRIMARY KEY,
                      width INTEGER DEFAULT 640,
                      height INTEGER DEFAULT 480,
                      fps INTEGER DEFAULT 30,
                      camera_index INTEGER DEFAULT 0,
                      codec TEXT DEFAULT 'H264')''')

        c.execute('INSERT OR IGNORE INTO video_settings (id) VALUES (1)')

        admin_username = app.config['ADMIN_CREDENTIALS']['username']
        admin_pwd = app.config['ADMIN_CREDENTIALS']['password']
        c.execute('''INSERT OR IGNORE INTO users 
                     (id, username, password, is_admin) 
                     VALUES (0, ?, ?, TRUE)''',
                  (admin_username, admin_pwd))

        conn.commit()
    except Exception as e:
        print(f"Database error: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

# 用户类
class User(UserMixin):
    def __init__(self, user_id, username, is_admin=False):
        self.id = user_id
        self.username = username
        self.is_admin = is_admin

# 登录管理器
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        if user:
            return User(user[0], user[1], bool(user[2]))
        return None
    except Exception as e:
        print(f"Load user error: {str(e)}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

# 摄像头类
class VideoCamera:
    def __init__(self):
        self.lock = Lock()
        self.frame_size = 0
        self.last_calc_time = time.time()
        self.bandwidth = 0
        self.last_frame_time = time.time()
        self.actual_fps = 0
        self.available_cameras = []
        self.update_settings()
        self.discover_cameras()

    def discover_cameras(self):
        self.available_cameras = []
        for i in range(0, 4):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.available_cameras.append(i)
                cap.release()
        print(f"Detected cameras: {self.available_cameras}")

    def update_settings(self):
        try:
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute('SELECT width, height, fps, camera_index, codec FROM video_settings WHERE id=1')
            settings = c.fetchone()

            with self.lock:
                self.width = settings[0] if settings else 640
                self.height = settings[1] if settings else 480
                self.target_fps = settings[2] if settings else 30
                self.camera_index = settings[3] if settings else 0
                self.codec = settings[4] if settings else 'H264'

                if hasattr(self, 'cap'):
                    self.cap.release()

                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    raise RuntimeError(f"无法打开摄像头索引 {self.camera_index}")

                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

                fourcc = cv2.VideoWriter_fourcc(*self.codec)
                self.codec_params = {
                    'fourcc': fourcc,
                    'fps': self.target_fps,
                    'frameSize': (self.width, self.height)
                }

                print(f"Camera settings updated: {self.width}x{self.height}@{self.target_fps}fps, codec: {self.codec}")
        except Exception as e:
            print(f"Camera settings error: {str(e)}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()

    def get_frame(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_frame_time
            if elapsed < 1.0 / self.target_fps:
                time.sleep((1.0 / self.target_fps) - elapsed)

            success, frame = self.cap.read()
            if not success:
                return None, None

            now = time.time()
            self.actual_fps = 1.0 / (now - self.last_frame_time)
            self.last_frame_time = now

            if self.codec == 'H264':
                ret, encoded_frame = cv2.imencode('.h264', frame, [
                    int(cv2.IMWRITE_VIDEO_FRAMERATE), self.target_fps,
                    int(cv2.IMWRITE_H264_QUALITY), 23
                ])
            else:
                ret, encoded_frame = cv2.imencode('.jpg', frame, [
                    int(cv2.IMWRITE_JPEG_QUALITY), 80
                ])

            if not ret:
                return None, None

            frame_bytes = encoded_frame.tobytes()

            self.frame_size = len(frame_bytes)
            if now - self.last_calc_time >= 1:
                self.bandwidth = (self.frame_size * 8 * self.actual_fps) / 1_000_000
                self.last_calc_time = now

            return frame_bytes, self.actual_fps


# 路由定义
@app.route('/')
@login_required
def index():
    return render_template('stream.html', 
                           video_camera=video_camera,
                           bandwidth=video_camera.bandwidth)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('请输入用户名和密码')
            return redirect(url_for('login'))

        try:
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute('SELECT id, password, is_admin FROM users WHERE username = ?', (username,))
            user = c.fetchone()

            if user and check_password_hash(user[1], password):
                login_user(User(user[0], username, bool(user[2])))
                next_page = url_for('admin_panel') if user[2] else url_for('index')
                return redirect(next_page)
            else:
                flash('用户名或密码错误')
        except Exception as e:
            flash('登录出错，请重试')
            print(f"Login error: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        invite_code = request.form.get('invite_code')

        if not all([username, password, invite_code]):
            flash('请填写完整信息')
            return redirect(url_for('register'))

        try:
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()

            c.execute('SELECT 1 FROM invite_codes WHERE code = ?', (invite_code,))
            if not c.fetchone():
                flash('无效的邀请码')
                return redirect(url_for('register'))

            hashed_pwd = generate_password_hash(password)
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                      (username, hashed_pwd))
            conn.commit()
            flash('注册成功，请登录')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('用户名已存在')
        except Exception as e:
            flash('注册出错，请重试')
            print(f"Register error: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

    return render_template('register.html')

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        abort(403)

    try:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()

        c.execute('SELECT id, username FROM users WHERE id != 0')
        users = c.fetchall()

        c.execute('SELECT code FROM invite_codes')
        codes = [row[0] for row in c.fetchall()]

        c.execute('SELECT width, height, fps, camera_index, codec FROM video_settings WHERE id=1')
        settings = c.fetchone()

        return render_template('admin.html',
                               users=users,
                               codes=codes,
                               width=settings[0],
                               height=settings[1],
                               fps=settings[2],
                               camera_index=settings[3],
                               codec=settings[4],
                               available_cameras=video_camera.available_cameras,
                               bandwidth=video_camera.bandwidth,
                               actual_fps=video_camera.actual_fps)
    except Exception as e:
        flash('加载管理面板出错')
        print(f"Admin panel error: {str(e)}")
        return redirect(url_for('index'))
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/admin/action', methods=['POST'])
@login_required
def admin_action():
    if not current_user.is_admin:
        abort(403)

    action = request.form.get('action')

    try:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()

        if action == 'delete_user':
            user_id = request.form.get('user_id')
            c.execute('DELETE FROM users WHERE id = ?', (user_id,))
            flash('用户已删除')

        elif action == 'add_code':
            new_code = request.form.get('new_code')
            if not new_code:
                flash('请输入邀请码')
            else:
                try:
                    c.execute('INSERT INTO invite_codes (code) VALUES (?)', (new_code,))
                    flash('邀请码添加成功')
                except sqlite3.IntegrityError:
                    flash('邀请码已存在')

        elif action == 'delete_code':
            code = request.form.get('code')
            c.execute('DELETE FROM invite_codes WHERE code = ?', (code,))
            flash('邀请码已删除')

        elif action == 'update_settings':
            try:
                width = int(request.form.get('width', 640))
                height = int(request.form.get('height', 480))
                fps = int(request.form.get('fps', 30))
                camera_index = int(request.form.get('camera_index', 0))
                codec = request.form.get('codec', 'H264')

                c.execute('''UPDATE video_settings 
                             SET width=?, height=?, fps=?, camera_index=?, codec=?
                             WHERE id=1''', 
                          (width, height, fps, camera_index, codec))
                video_camera.update_settings()
                flash('视频设置已更新')
            except ValueError:
                flash('请输入有效的数字')

        conn.commit()
    except Exception as e:
        flash('操作失败')
        print(f"Admin action error: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('admin_panel'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录')
    return redirect(url_for('login'))

def gen(camera):
    while True:
        frame_bytes, actual_fps = camera.get_frame()
        if frame_bytes is None:
            break
        yield (b'--frame\r\n'
               b'Content-Type: video/h264\r\n\r\n' + frame_bytes + b'\r\n\r\n')

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(gen(video_camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_camera_info')
@login_required
def get_camera_info():
    return jsonify({
        'width': video_camera.width,
        'height': video_camera.height,
        'fps': video_camera.actual_fps,
        'bandwidth': video_camera.bandwidth,
        'codec': video_camera.codec
    })

if __name__ == '__main__':
    init_db()
    global video_camera  # 声明为全局变量
    video_camera = VideoCamera()
    app.run(host='0.0.0.0', port=5000, threaded=True)