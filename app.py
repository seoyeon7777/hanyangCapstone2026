from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')  # ← 수정


@app.route('/result')            # ← 새 라우트 추가
def result():
    return render_template('result.html')


if __name__ == '__main__':
    app.run(debug=True)