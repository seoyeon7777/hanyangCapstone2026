from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from models.fitting_model import match_avatar, calc_shape_keys, calc_fit_score, calc_pressure

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/result')
def result():
    return render_template('result.html')

@app.route('/api/fit/analyze', methods=['POST'])
def analyze():
    body         = request.get_json()
    height       = body['height']
    weight       = body['weight']
    garment_type = body['garment_type']
    measurements = body['measurements']
    fabric       = body['fabric']

    avatar_size               = match_avatar(height, weight)
    shape_keys                = calc_shape_keys(garment_type, measurements)
    fit_score                 = calc_fit_score(shape_keys)
    pressure_data, fit_result = calc_pressure(shape_keys)

    return jsonify({
        "avatar_size":   avatar_size,
        "shape_keys":    shape_keys,
        "fit_score":     fit_score,
        "fit_result":    fit_result,
        "pressure_data": pressure_data,
        "images": {
            "silhouette_front": "/outputs/test/silhouette_front.png",
            "silhouette_side":  "/outputs/test/silhouette_side.png",
            "silhouette_back":  "/outputs/test/silhouette_back.png",
            "heatmap":          "/outputs/test/heatmap.png"
        }
    })

if __name__ == '__main__':
    app.run(debug=True)