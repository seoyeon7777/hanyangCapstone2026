from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from models.fitting_model import match_avatar, calc_shape_keys, calc_fit_score, calc_pressure
from services.blender_runner import run_blender
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/result')
def result():
    return render_template('result.html')

@app.route('/outputs/<path:filename>')
def outputs(filename):
    base = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(os.path.join(base, 'outputs'), filename)

@app.route('/api/fit/analyze', methods=['POST'])
def analyze():
    body         = request.get_json()
    height       = body['height']
    weight       = body['weight']
    garment_type = body.get('garment_type', 'tshirt')
    measurements = body.get('measurements', {})
    fabric       = body.get('fabric', {})
 
    avatar_size               = match_avatar(height, weight)
    shape_keys                = calc_shape_keys(garment_type, measurements)
    fit_score                 = calc_fit_score(shape_keys)
    pressure_data, fit_result = calc_pressure(shape_keys, fabric)

    # Blender 렌더링
    job_id = f"{avatar_size}_{height}_{weight}"
    images = run_blender(avatar_size, shape_keys, job_id)

    return jsonify({
        "avatar_size":   avatar_size,
        "shape_keys":    shape_keys,
        "fit_score":     fit_score,
        "fit_result":    fit_result,
        "pressure_data": pressure_data,
        "images": {
            "silhouette_front": f"/outputs/{job_id}/silhouette_front.png"
        }
    })

if __name__ == '__main__':
    app.run(debug=True)