#!/bin/bash

# 5000번 포트에서 실행중인 프로세스 종료
fuser -k 5000/tcp

# 가상환경 활성화 후 애플리케이션 실행
source venv/bin/activate
pip install -r requirements.txt
python app.py
