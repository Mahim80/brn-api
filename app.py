import requests, re, io, time
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageFilter

app = Flask(__name__)

# ==================== কনফিগারেশন ====================
OCR_API_KEY = 'K88372746588957'
BASE_URL = "https://everify.bdris.gov.bd"

def solve_captcha(session, captcha_url):
    try:
        resp = session.get(captcha_url, timeout=10)
        img = Image.open(io.BytesIO(resp.content))
        
        # ইমেজ প্রসেসিং: বড় করা এবং পরিষ্কার করা
        img = img.convert('L') # সাদা-কালো করা
        img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
        img = img.filter(ImageFilter.SHARPEN) # শার্প করা
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        payload = {'apikey': OCR_API_KEY, 'language': 'eng', 'OCREngine': '2'}
        files = {'file': ('captcha.png', img_byte_arr, 'image/png')}
        
        ocr_resp = requests.post('https://api.ocr.space/parse/image', data=payload, files=files, timeout=15)
        parsed_text = ocr_resp.json().get('ParsedResults', [{}])[0].get('ParsedText', '')
        
        # অংক খুঁজে বের করা (যেমন: 10 + 5)
        parsed_text = parsed_text.replace(' ', '').replace('=', '')
        match = re.search(r'(\d+)([\+\-\*])(\d+)', parsed_text)
        
        if match:
            a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
            if op == '+': return a + b
            if op == '-': return a - b
            if op == '*': return a * b
        return None
    except: return None

@app.route('/verify', methods=['GET'])
def api_verify():
    brn = request.args.get('brn')
    dob = request.args.get('dob')
    if not brn or not dob: return jsonify({"status": 400, "message": "Missing params"}), 400
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        response = session.get(BASE_URL, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        token = soup.find('input', {'name': '__RequestVerificationToken'})['value']
        captcha_url = BASE_URL + soup.find('img', {'id': 'CaptchaImage'})['src']
        captcha_de_text = re.search(r't=([^&]+)', captcha_url).group(1)

        # ৩ বার চেষ্টা করবে ক্যাপচা সলভ করার জন্য
        solved_val = None
        for _ in range(3):
            solved_val = solve_captcha(session, captcha_url)
            if solved_val is not None: break
            time.sleep(1) # ১ সেকেন্ড বিরতি

        if solved_val is None: return jsonify({"status": 404, "message": "Captcha failed to read"}), 404

        search_response = session.post(f"{BASE_URL}/UBRNVerification/Search", data={
            "__RequestVerificationToken": token, "UBRN": brn, "BirthDate": dob,
            "captchaDeText": captcha_de_text, "CaptchaInputText": str(solved_val)
        }, timeout=20)

        if "No data found" in search_response.text:
            return jsonify({"status": 404, "message": "No record found"}), 404

        # সাকসেস হলে রেসপন্স
        return jsonify({
            "status": 200, 
            "success": True, 
            "message": "Data Found",
            "html_data": search_response.text
        })
    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
