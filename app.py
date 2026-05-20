# from flask import Flask, render_template, request

# app = Flask(__name__)

# @app.route('/')
# def index():
#     return render_template('index.html')  # ← 수정


# @app.route('/result')            # ← 새 라우트 추가
# def result():
#     return render_template('result.html')


# if __name__ == '__main__':
#     app.run(debug=True)


from flask import Flask, render_template, request
import pandas as pd
import numpy as np

app = Flask(__name__)
df = pd.read_excel('data/신체사이즈표.xlsx', sheet_name='Sizedata')

def score_class(s):
    if s >= 75: return 'good'
    if s >= 55: return 'ok'
    return 'warn'

def analyze_fit(height, weight, shoulder=None, arm=None, chest=None):
    sub = df[df['성별'] == '여'].copy()

    sub['dist'] = (
        ((sub['키(cm)'] - height) / sub['키(cm)'].std()) ** 2 +
        ((sub['몸무게(kg)'] - weight) / sub['몸무게(kg)'].std()) ** 2
    )
    if chest:
        sub['dist'] += ((sub['가슴둘레(cm)'] - chest) / sub['가슴둘레(cm)'].std()) ** 2
    if shoulder:
        sub['dist'] += ((sub['어깨가쪽사이길이(cm)'] - shoulder) / sub['어깨가쪽사이길이(cm)'].std()) ** 2
    if arm:
        sub['dist'] += ((sub['팔길이(cm)'] - arm) / sub['팔길이(cm)'].std()) ** 2

    neighbors = sub.nsmallest(30, 'dist')
    rec_size = neighbors['예측사이즈'].mode()[0]
    size_group = sub[sub['예측사이즈'] == rec_size]

    def fit_score(user_val, col):
        if user_val is None:
            user_val = neighbors[col].mean()
        mean = size_group[col].mean()
        std = size_group[col].std()
        if std == 0:
            return 100
        z = abs(user_val - mean) / std
        return max(0, round(100 - z * 28))

    shoulder_score = fit_score(shoulder, '어깨가쪽사이길이(cm)')
    chest_score    = fit_score(chest,    '가슴둘레(cm)')
    arm_score      = fit_score(arm,      '팔길이(cm)')
    waist_val      = neighbors['허리둘레(cm)'].mean()
    waist_score    = fit_score(waist_val, '허리둘레(cm)')
    overall        = round((shoulder_score + chest_score + arm_score + waist_score) / 4)

    parts = [('어깨', shoulder_score), ('가슴', chest_score),
             ('허리', waist_score), ('팔길이', arm_score)]
    good = [p for p, s in parts if s >= 75]
    warn = [p for p, s in parts if s < 55]

    review_parts = []
    if good:
        review_parts.append(f"{'·'.join(good)} 라인이 잘 맞습니다.")
    if warn:
        if '팔길이' in warn:
            review_parts.append("팔길이가 약간 길어 소매를 걷어 입는 것을 권장합니다.")
        else:
            review_parts.append(f"{'·'.join(warn)} 부분은 약간의 조정이 필요할 수 있습니다.")
    if not review_parts:
        review_parts.append("전반적으로 체형에 잘 맞는 사이즈입니다.")

    return {
        'score': overall,
        'rec_size': rec_size,
        'shoulder_score': shoulder_score,
        'chest_score': chest_score,
        'waist_score': waist_score,
        'arm_score': arm_score,
        'shoulder_cls': score_class(shoulder_score),
        'chest_cls':    score_class(chest_score),
        'waist_cls':    score_class(waist_score),
        'arm_cls':      score_class(arm_score),
        'review': ' '.join(review_parts),
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/result')
def result():
    height   = float(request.args.get('height', 165))
    weight   = float(request.args.get('weight', 60))
    shoulder = float(v) if (v := request.args.get('shoulder')) else None
    arm      = float(v) if (v := request.args.get('arm'))      else None
    chest    = float(v) if (v := request.args.get('chest'))    else None

    fit = analyze_fit(height, weight, shoulder, arm, chest)

    level = ('✓ 좋은 핏입니다' if fit['score'] >= 75
             else '△ 보통 핏입니다' if fit['score'] >= 60
             else '✕ 사이즈 조정 권장')
    level_color = ('#2e7d32' if fit['score'] >= 75
                   else '#f59e0b' if fit['score'] >= 60
                   else '#c8432a')

    return render_template('result.html', level=level, level_color=level_color, **fit)

if __name__ == '__main__':
    app.run(debug=True)
