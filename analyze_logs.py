import boto3
import pandas as pd
from datetime import datetime

# 1. DynamoDB 접속
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SentimentAnalysisLog')

def get_stats():
    # 2. 모든 데이터 가져오기 (Scan)
    # 데이터가 많아지면 필터링이 필요하지만, 지금은 전체를 가져옵니다.
    response = table.scan()
    items = response.get('Items', [])

    if not items:
        print("데이터가 없습니다. 웹사이트에서 테스트를 먼저 진행해주세요!")
        return

    # 3. Pandas 데이터프레임으로 변환 (분석하기 편하게)
    df = pd.DataFrame(items)

    # 숫자로 저장된 timestamp를 읽기 쉬운 날짜로 변환
    df['datetime'] = pd.to_datetime(df['timestamp'].astype(float), unit='s')
    
    # 4. 간단한 통계 계산
    total_count = len(df)
    label_counts = df['label'].value_counts()
    avg_latency = df['latency_ms'].astype(float).mean()

    print("=== 감성 분석 서비스 실시간 리포트 ===")
    print(f"총 분석 횟수: {total_count}회")
    print(f"평균 응답 속도: {avg_latency:.2f} ms")
    print("\n--- [감성 분포] ---")
    for label, count in label_counts.items():
        percentage = (count / total_count) * 100
        print(f" {label}: {count}건 ({percentage:.1f}%)")
    
    print("\n--- [최근 5건 로그] ---")
    print(df[['datetime', 'label', 'confidence']].tail(5))

if __name__ == "__main__":
    get_stats()