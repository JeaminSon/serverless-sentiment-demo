import boto3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# 한글 깨짐 방지 설정 (Windows 기준)
plt.rc('font', family='Malgun Gothic')
plt.rcParams['axes.unicode_minus'] = False

# 1. DynamoDB 접속
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SentimentAnalysisLog')

def visualize():
    # 2. 데이터 가져오기 및 변환
    response = table.scan()
    df = pd.DataFrame(response.get('Items', []))
    
    if df.empty:
        print("데이터가 없습니다!")
        return

    df['datetime'] = pd.to_datetime(df['timestamp'].astype(float), unit='s')
    df['latency_ms'] = df['latency_ms'].astype(float)
    df = df.sort_values('datetime')

    # 3. 그래프 그리기 (1행 2열 구성)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 왼쪽: 감성 분포 (Pie Chart)
    label_counts = df['label'].value_counts()
    ax1.pie(label_counts, labels=label_counts.index, autopct='%1.1f%%', 
            colors=sns.color_palette('pastel'), startangle=140)
    ax1.set_title("전체 감성 분포 비중")

    # 오른쪽: 응답 속도 추이 (Line Chart)
    sns.lineplot(x='datetime', y='latency_ms', data=df, marker='o', ax=ax2)
    ax2.set_title("시간별 응답 지연 시간(ms) 추이")
    ax2.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    print("🎨 그래프를 생성했습니다. 팝업 창을 확인하세요!")
    plt.show()

if __name__ == "__main__":
    visualize()