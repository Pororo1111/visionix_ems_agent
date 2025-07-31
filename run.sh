#!/bin/bash
# 가상환경 활성화 후 애플리케이션 실행
source venv/bin/activate
pip install -r requirements.txt
python app.py
