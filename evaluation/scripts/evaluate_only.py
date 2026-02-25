"""
평가만 실행하는 스크립트
미리 생성된 답변 파일(JSON)을 로드하여 Ragas 평가만 수행
"""
import json
import sys
from pathlib import Path
from typing import Dict, List

from colorama import Fore, Style, init
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src.config import validate_env

init(autoreset=True)


def print_header(text: str):
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}{text:^60}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


def print_progress(text: str):
    print(f"{Fore.YELLOW}▶ {text}{Style.RESET_ALL}")


def print_success(text: str):
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str):
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")


def print_metric(name: str, value: float):
    if value >= 0.8:
        color = Fore.GREEN
    elif value >= 0.6:
        color = Fore.YELLOW
    else:
        color = Fore.RED
    
    bar_length = int(value * 40)
    bar = "█" * bar_length + "░" * (40 - bar_length)
    print(f"{name:20s} {color}{bar}{Style.RESET_ALL} {value:.4f}")


def main():
    print_header("🔬 Ragas 평가 전용 스크립트")
    
    # 환경 변수 검증
    try:
        validate_env()
        print_success("환경 변수 검증 완료")
    except Exception as e:
        print_error(f"환경 변수 검증 실패: {str(e)}")
        sys.exit(1)
    
    # 답변 파일 찾기
    base_dir = Path(__file__).parent
    answers_file = base_dir / "generated_answers.json"
    
    if not answers_file.exists():
        print_error(f"답변 파일을 찾을 수 없습니다: {answers_file}")
        print("\n💡 답변 파일을 먼저 생성해야 합니다:")
        print("   python evaluate_single.py --config baseline")
        print("   (이제 자동으로 generated_answers.json 파일이 생성됩니다)")
        sys.exit(1)
    
    # 답변 로드
    print_progress(f"답변 파일 로드 중: {answers_file}")
    with open(answers_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = data['results']
    config_name = data.get('config', 'unknown')
    
    print_success(f"{len(results)}개 답변 로드 완료 (설정: {config_name})")
    
    # Ragas 평가
    print_progress("Ragas 평가 준비 중...")
    
    dataset = Dataset.from_list(results)
    
    eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    eval_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    metrics = [
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ]
    
    print(f"\n{Fore.CYAN}평가 지표:{Style.RESET_ALL}")
    print("  • Faithfulness (충실도): 답변이 검색된 문서에 근거하는가")
    print("  • Answer Relevancy (답변 관련성): 답변이 질문과 관련 있는가")
    print("  • Context Precision (컨텍스트 정밀도): 검색이 정확한가")
    print("  • Context Recall (컨텍스트 재현율): 필요한 정보를 모두 검색했는가")
    print()
    
    print_progress("평가 진행 중 (시간이 다소 걸릴 수 있습니다)...")
    
    try:
        eval_result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=eval_llm,
            embeddings=eval_embeddings,
        )
        print_success("평가 완료!")
        
        # EvaluationResult에서 점수 추출 - 50개 전체 평균 계산
        try:
            df = eval_result.to_pandas()
            # 각 metric 열의 평균을 계산
            metrics_dict = {}
            for col in df.columns:
                if col not in ['user_input', 'retrieved_contexts', 'response', 'reference']:
                    metrics_dict[col] = df[col].mean()
        except Exception as e:
            print_error(f"점수 추출 실패: {e}")
            metrics_dict = {}
            for metric in metrics:
                metric_name = metric.name
                if hasattr(eval_result, metric_name):
                    metrics_dict[metric_name] = getattr(eval_result, metric_name)
        
        # 결과 출력
        print_header(f"📊 평가 결과 - {config_name}")
        
        print(f"{Fore.CYAN}【 평가 지표별 점수 】{Style.RESET_ALL}\n")
        
        for metric_name, score in metrics_dict.items():
            if isinstance(score, (int, float)):
                print_metric(metric_name, score)
        
        numeric_scores = [v for v in metrics_dict.values() if isinstance(v, (int, float))]
        if numeric_scores:
            avg_score = sum(numeric_scores) / len(numeric_scores)
            print(f"\n{Fore.MAGENTA}{'─'*60}{Style.RESET_ALL}")
            print_metric("전체 평균 점수", avg_score)
            print(f"{Fore.MAGENTA}{'─'*60}{Style.RESET_ALL}\n")
        
        # 결과 저장
        output_file = base_dir / f"evaluation_{config_name}.json"
        output_data = {
            'config': config_name,
            'metrics': {k: float(v) if isinstance(v, (int, float)) else str(v) 
                       for k, v in metrics_dict.items()},
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print_success(f"결과 저장: {output_file}")
        
        print_header("✅ 평가 완료")
        
    except Exception as e:
        print_error(f"평가 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
