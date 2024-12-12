import os
import subprocess
import requests
import time
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('server_ex.env')

# 환경 변수 읽기
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
SERVER_NAME = os.getenv("SERVER_NAME", "Unknown Server")

if not WEBHOOK_URL:
    raise ValueError("SLACK_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")

# 설정 값
CHECK_INTERVAL = 60  # 1분 간격
ALERT_THRESHOLD = 5000  # 5GB (MB 단위)
alert_sent_for_idle = False  # GPU 사용 가능 상태 메시지 중복 방지 플래그

# 데이터 저장 경로 설정
LOG_DIR = "monitor_log"
LOG_FILE = os.path.join(LOG_DIR, "gpu_status.log")
os.makedirs(LOG_DIR, exist_ok=True)

def get_gpu_memory():
    """GPU 메모리 사용량 조회 (단일 GPU)"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        used, total = map(int, result.stdout.strip().split("\n")[0].split(","))
        return used, total
    except Exception as e:
        return 0, 0  # 오류 발생 시 기본값 반환

def save_to_file(data):
    """GPU 상태를 파일에 저장"""
    with open(LOG_FILE, "a") as f:
        f.write(data + "\n")

def send_to_slack(message):
    """슬랙으로 메시지 전송"""
    full_message = f"🖥️ *{SERVER_NAME}*\n{message}"
    requests.post(WEBHOOK_URL, json={"text": full_message})

def monitor_gpu():
    global alert_sent_for_idle
    previous_used = None
    first_run = True  # 첫 실행 여부 플래그

    while True:
        used, total = get_gpu_memory()
        if total == 0:
            print("[GPU Monitor] GPU가 감지되지 않았습니다.")
            time.sleep(CHECK_INTERVAL)
            continue

        # 첫 실행 시 상태 보고
        if first_run:
            initial_message = f"🔍 GPU 메모리 사용 현황: {used}MB / {total}MB"
            send_to_slack(initial_message)
            save_to_file(initial_message)
            first_run = False

        # 사용량이 0MB로 감소한 경우 처리 (학습 완료)
        if used == 0 and previous_used != 0:
            combined_message = (
                f"🔹 GPU 사용량: {used}MB / {total}MB\n"
                f"이전 사용량: {previous_used}MB → 현재 사용량: {used}MB\n"
                f"✅ <{SERVER_NAME}> 사용 가능!"
            )
            send_to_slack(combined_message)
            save_to_file(combined_message)
            alert_sent_for_idle = True
            previous_used = used  # 상태 갱신
            time.sleep(CHECK_INTERVAL)
            continue

        # GPU 사용량이 0에서 증가한 경우 처리 (학습 시작)
        if used > 0 and previous_used == 0 and alert_sent_for_idle:
            start_message = (
                f"🔄 <{SERVER_NAME}>에서 학습이 시작되었습니다!\n"
                f"🔹 GPU 사용량: {used}MB / {total}MB\n"
                f"이전 사용량: {previous_used}MB → 현재 사용량: {used}MB"
            )
            send_to_slack(start_message)
            save_to_file(start_message)
            alert_sent_for_idle = False

        # 사용량 변화 메시지 (임계치 기준)
        if previous_used is not None:
            change = abs(used - previous_used)
            if change >= ALERT_THRESHOLD:  # ALERT_THRESHOLD = 5000
                change_message = (
                    f"🔹 GPU 사용량: {used}MB / {total}MB\n"
                    f"이전 사용량: {previous_used}MB → 현재 사용량: {used}MB"
                )
                send_to_slack(change_message)
                save_to_file(change_message)

        # 상태 업데이트
        previous_used = used
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_gpu()
