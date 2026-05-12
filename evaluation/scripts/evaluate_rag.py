"""
RAG 시스템 평가 스크립트
Ragas 라이브러리를 사용한 질의응답 품질 평가
"""
import json
import sys
import asyncio
from datetime import datetime
from typing import Dict, List
from pathlib import Path

# 진행 상태 표시를 위한 유틸리티
from tqdm import tqdm
from colorama import Fore, Style, init

# Ragas imports
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

# 프로젝트 모듈
from src.chain.rag_chain import prepare_context, generate_answer
from src.config import validate_env

# Colorama 초기화 (Windows 호환)
init(autoreset=True)

def print_header(text: str):
    """헤더 출력"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}{text:^60}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

def print_progress(text: str):
    """진행 상태 출력"""
    print(f"{Fore.YELLOW}▶ {text}{Style.RESET_ALL}")

def print_success(text: str):
    """성공 메시지 출력"""
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")

def print_error(text: str):
    """에러 메시지 출력"""
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")

def print_metric(name: str, value: float):
    """평가 지표 출력"""
    # 점수에 따라 색상 변경
    if value >= 0.8:
        color = Fore.GREEN
    elif value >= 0.6:
        color = Fore.YELLOW
    else:
        color = Fore.RED
    
    bar_length = int(value * 40)
    bar = "█" * bar_length + "░" * (40 - bar_length)
    print(f"{name:20s} {color}{bar}{Style.RESET_ALL} {value:.4f}")

def load_test_dataset(filepath: str) -> List[Dict]:
    """테스트 데이터셋 로드"""
    print_progress(f"테스트 데이터셋 로드 중: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print_success(f"총 {len(data)}개의 테스트 케이스 로드 완료")
    return data

def generate_rag_responses(test_data: List[Dict]) -> List[Dict]:
    """RAG 시스템으로 답변 생성"""
    print_progress("RAG 시스템 답변 생성 중...")
    
    results = []
    
    # tqdm을 사용한 진행 표시
    for item in tqdm(test_data, desc="답변 생성", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'):
        question = item['question']
        
        try:
            # 컨텍스트 준비 및 답변 생성
            context_data = prepare_context(question)
            answer = generate_answer(context_data)
            
            # Ragas 평가에 필요한 형식으로 구성
            result = {
                'question': question,
                'answer': answer,
                'contexts': [context_data['context']],  # 리스트 형태로
                'ground_truth': item['ground_truth'],
            }
            results.append(result)
            
        except Exception as e:
            print_error(f"질문 처리 실패: {question[:50]}... - {str(e)}")
            # 실패해도 빈 답변으로 추가
            results.append({
                'question': question,
                'answer': "답변 생성 실패",
                'contexts': [""],
                'ground_truth': item['ground_truth'],
            })
    
    print_success(f"{len(results)}개 답변 생성 완료")
    return results

def evaluate_rag_system(results: List[Dict]) -> Dict:
    """Ragas를 사용한 RAG 시스템 평가"""
    print_progress("Ragas 평가 시작...")
    
    # Dataset 생성
    dataset = Dataset.from_list(results)
    
    # 평가용 LLM 및 Embeddings 설정 (Ragas 호환성)
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    
    eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    eval_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # 평가 지표 정의
    metrics = [
        faithfulness,           # 충실도: 답변이 컨텍스트에 근거하는가
        answer_relevancy,       # 답변 관련성: 답변이 질문과 관련 있는가
        context_precision,      # 컨텍스트 정밀도: 검색된 컨텍스트가 정확한가
        context_recall,         # 컨텍스트 재현율: 필요한 정보를 모두 검색했는가
    ]
    
    print(f"\n{Fore.CYAN}평가 지표:{Style.RESET_ALL}")
    print("  • Faithfulness (충실도): 답변이 검색된 문서에 근거하는가")
    print("  • Answer Relevancy (답변 관련성): 답변이 질문과 관련 있는가")
    print("  • Context Precision (컨텍스트 정밀도): 검색이 정확한가")
    print("  • Context Recall (컨텍스트 재현율): 필요한 정보를 모두 검색했는가")
    print()
    
    # 평가 실행 (진행 표시 포함) - LLM과 embeddings 명시적 전달
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
            result_dict = {}
            for col in df.columns:
                if col not in ['question', 'answer', 'contexts', 'ground_truth']: # Ragas 0.1.0 이후 변경된 컬럼명 반영
                    result_dict[col] = df[col].mean()
        except Exception as e:
            print_error(f"점수 추출 실패: {e}")
            result_dict = {}
            for metric in metrics:
                metric_name = metric.name
                result_dict[metric_name] = getattr(eval_result, metric_name)
        
        return result_dict
        
    except Exception as e:
        print_error(f"평가 중 오류 발생: {str(e)}")
        raise

def display_results(eval_result: Dict, output_file: str = None):
    """평가 결과 출력 및 저장"""
    print_header("📊 평가 결과")
    
    # 각 지표별 점수 출력
    metrics_dict = eval_result
    
    print(f"{Fore.CYAN}【 평가 지표별 점수 】{Style.RESET_ALL}\n")
    
    for metric_name, score in metrics_dict.items():
        if isinstance(score, (int, float)):
            print_metric(metric_name, score)
    
    # 전체 평균 점수 계산
    numeric_scores = [v for v in metrics_dict.values() if isinstance(v, (int, float))]
    if numeric_scores:
        avg_score = sum(numeric_scores) / len(numeric_scores)
        print(f"\n{Fore.MAGENTA}{'─'*60}{Style.RESET_ALL}")
        print_metric("전체 평균 점수", avg_score)
        print(f"{Fore.MAGENTA}{'─'*60}{Style.RESET_ALL}\n")
        
        # 점수 해석
        if avg_score >= 0.8:
            assessment = f"{Fore.GREEN}우수{Style.RESET_ALL} - RAG 시스템이 매우 잘 작동하고 있습니다!"
        elif avg_score >= 0.6:
            assessment = f"{Fore.YELLOW}양호{Style.RESET_ALL} - 개선의 여지가 있지만 적절하게 작동합니다."
        else:
            assessment = f"{Fore.RED}개선 필요{Style.RESET_ALL} - 시스템 개선이 필요합니다."
        
        print(f"종합 평가: {assessment}\n")
    
    # 결과 저장
    if output_file:
        save_results(metrics_dict, output_file)

def save_results(results: Dict, output_file: str):
    """평가 결과를 JSON 파일로 저장"""
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'metrics': {k: float(v) if isinstance(v, (int, float)) else str(v) 
                   for k, v in results.items()},
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print_success(f"결과 저장 완료: {output_file}")

def main():
    """메인 실행 함수"""
    print_header("🛫 Japan Tour RAG 체인 평가 (Ragas)")
    
    # 환경 변수 검증
    try:
        validate_env()
        print_success("환경 변수 검증 완료")
    except Exception as e:
        print_error(f"환경 변수 검증 실패: {str(e)}")
        sys.exit(1)
    
    # 파일 경로 설정
    test_dataset_path = Path(__file__).parent / "test_dataset.json"
    output_path = Path(__file__).parent / "evaluation_results.json"
    
    try:
        # 1. 테스트 데이터셋 로드
        test_data = load_test_dataset(str(test_dataset_path))
        
        # 2. RAG 시스템으로 답변 생성
        rag_results = generate_rag_responses(test_data)
        
        # 3. Ragas로 평가
        eval_result = evaluate_rag_system(rag_results)
        
        # 4. 결과 출력 및 저장
        display_results(eval_result, str(output_path))
        
        print_header("✅ 평가 완료")
        
    except FileNotFoundError as e:
        print_error(f"파일을 찾을 수 없습니다: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"예상치 못한 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
