from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "서버 정상 동작 중!"

if __name__ == '__main__':
    app.run(debug=True)