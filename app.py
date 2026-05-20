import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from models.fitting_model import match_avatar, calc_shape_keys, calc_scale, calc_fit_score, calc_pressure
from services.blender_runner import run_blender

app = Flask(__name__)
CORS(app)

# 의상 타입 → assets/clothing/ 파일명 매핑
GARMENT_FILE_MAP = {
    'tshirt':  'top',
    'shirt':   'top',
    'hoodie':  'top',
    'jacket':  'top',
    'coat':    'top',
    'pants':   'pants',
}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/result')
def result():
    return render_template('result.html')


@app.route('/outputs/<path:filename>')
def serve_output(filename):
    """Blender가 생성한 렌더링 이미지 서빙"""
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    return send_from_directory(outputs_dir, filename)


@app.route('/api/fit/analyze', methods=['POST'])
def analyze():
    try:
        body         = request.get_json()
        height       = body['height']
        weight       = body['weight']
        garment_type = body.get('garment_type', 'tshirt') or 'tshirt'
        measurements = body.get('measurements', {})
        fabric       = body.get('fabric', {})

        avatar_size               = match_avatar(height, weight)
        shape_keys                = calc_shape_keys(garment_type, measurements, avatar_size)
        scale                     = calc_scale(garment_type, measurements)
        fit_score                 = calc_fit_score(shape_keys, fabric)
        pressure_data, fit_result = calc_pressure(shape_keys, fabric)

        garment_file = GARMENT_FILE_MAP.get(garment_type, garment_type)

        job_id, output_dir = run_blender({
            "avatar_size":   avatar_size,
            "garment_type":  garment_file,   # 'tshirt' → 'top'
            "shape_keys":    shape_keys,
            "fabric":        fabric,
        })

        return jsonify({
            "avatar_size":   avatar_size,
            "shape_keys":    shape_keys,
            "scale":         scale,
            "fit_score":     fit_score,
            "fit_result":    fit_result,
            "pressure_data": pressure_data,
            "images": {
                "silhouette_front": f"/outputs/{job_id}/silhouette_front.png",
                "silhouette_right": f"/outputs/{job_id}/silhouette_right.png",
                "silhouette_back":  f"/outputs/{job_id}/silhouette_back.png",
                "silhouette_left":  f"/outputs/{job_id}/silhouette_left.png",
            }
        })

    except RuntimeError as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    except KeyError as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"필수 입력값 누락: {e}"}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, threaded=False, use_reloader=False)
