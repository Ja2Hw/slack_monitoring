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

# 데이터 저장 경로 설정
LOG_DIR = "monitor_log"
LOG_FILE = os.path.join(LOG_DIR, "gpu_status.log")
os.makedirs(LOG_DIR, exist_ok=True)

def get_all_gpu_memory():
    """모든 GPU의 메모리 사용량 조회"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split("\n")
        gpu_memory = []
        for line in lines:
            used, total = map(int, line.split(","))
            gpu_memory.append((used, total))
        return gpu_memory
    except Exception as e:
        print(f"GPU 메모리 조회 중 오류 발생: {e}")
        return []

def save_to_file(data):
    """GPU 상태를 파일에 저장"""
    with open(LOG_FILE, "a") as f:
        f.write(data + "\n")

def send_to_slack(message):
    """슬랙으로 메시지 전송"""
    full_message = f"🖥️ *{SERVER_NAME}*\n{message}"
    requests.post(WEBHOOK_URL, json={"text": full_message})

def monitor_gpu():
    previous_states = []  # 이전 상태 저장
    first_run = True

    while True:
        gpu_memory = get_all_gpu_memory()
        if not gpu_memory:
            print("[GPU Monitor] GPU가 감지되지 않았습니다.")
            time.sleep(CHECK_INTERVAL)
            continue

        message_lines = []  # 슬랙 메시지 라인
        changes_detected = False  # 상태 변화 감지 여부

        for gpu_index, (used, total) in enumerate(gpu_memory):
            emoji = f"{gpu_index}️⃣"  # GPU 번호 이모지
            if len(previous_states) <= gpu_index:
                previous_states.append(None)  # 이전 상태 초기화

            previous_used = previous_states[gpu_index]
            status_line = f"{emoji} GPU {gpu_index}: {used}MB / {total}MB"

            # 상태 변화 감지 (사용량 변화량 5000MB 이상)
            if previous_used is not None:
                change = abs(used - previous_used)

                # 사용 가능 상태 변화
                if previous_used != 0 and used == 0:
                    changes_detected = True
                    status_line += f" ✅ 사용 가능 (변화: {previous_used}MB → {used}MB)"

                # 사용 시작 조건: 5000MB 이상의 변화
                elif previous_used == 0 and used > 0 and change >= ALERT_THRESHOLD:
                    changes_detected = True
                    status_line += f" 🔄 사용 시작 (변화: {previous_used}MB → {used}MB)"

                # 일반적인 사용량 변화 알림
                elif change >= ALERT_THRESHOLD:
                    changes_detected = True
                    status_line += f" (변화: {previous_used}MB → {used}MB)"

            # 상태 업데이트
            previous_states[gpu_index] = used
            message_lines.append(status_line)

        # 슬랙 알림 전송
        if first_run or changes_detected:
            full_message = "\n".join(message_lines)
            send_to_slack(full_message)
            save_to_file(full_message)

        first_run = False
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_gpu()
