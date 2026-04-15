from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from models.fitting_model import match_avatar, calc_shape_keys

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')  # ← 수정


@app.route('/result')            # ← 새 라우트 추가
def result():
    return render_template('result.html')


# 데이터 받아서 처리하는 API
@app.route('/api/fit/analyze', methods=['POST'])
def analyze():
    body = request.get_json()

    # 프론트에서 받는 데이터
    height       = body['height']        # 키
    weight       = body['weight']        # 몸무게
    garment_type = body['garment_type']  # 의상 종류
    measurements = body['measurements']  # 치수
    fabric       = body['fabric']        # 원단

    # 지금은 더미 데이터 반환
    # 나중에 Blender 연결되면 여기서 실제 처리
    return jsonify({
        "avatar_size": "M",
        "fit_result": "tight",
        "pressure_data": {
            "chest":    {"value": 0.82, "level": "high"},
            "waist":    {"value": 0.45, "level": "medium"},
            "shoulder": {"value": 0.21, "level": "low"}
        },
        "images": {
            "silhouette_front": "/outputs/test/silhouette_front.png",
            "silhouette_side":  "/outputs/test/silhouette_side.png",
            "silhouette_back":  "/outputs/test/silhouette_back.png",
            "heatmap":          "/outputs/test/heatmap.png"
        }
    })


if __name__ == '__main__':
    app.run(debug=True)