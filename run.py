import os

from dotenv import load_dotenv

from app import create_app

load_dotenv()

app = create_app()

if __name__ == '__main__':
    # Using Port 5001 to guarantee macOS compatibility without AirPlay conflicts
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5001')), debug=True)
