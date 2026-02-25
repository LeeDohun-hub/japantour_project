"""
단일 최적화 버전 평가 스크립트
특정 설정으로만 평가를 실행
"""
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from tqdm import tqdm
from colorama import Fore, Style, init
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

from src.chain.optimized_rag_chain import prepare_context, generate_answer
from src.config import validate_env
from src.optimization_config import get_config, ALL_CONFIGS

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


def load_test_dataset(filepath: str) -> List[Dict]:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def generate_rag_responses(test_data: List[Dict], config) -> List[Dict]:
    results = []
    
    for item in tqdm(test_data, desc="답변 생성", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}'):
        question = item['question']
        
        try:
            context_data = prepare_context(question, config)
            answer = generate_answer(context_data, config)
            
            result = {
                'question': question,
                'answer': answer,
                'contexts': [context_data['context']],
                'ground_truth': item['ground_truth'],
            }
            results.append(result)
            
        except Exception as e:
            print_error(f"질문 처리 실패: {question[:50]}... - {str(e)}")
            results.append({
                'question': question,
                'answer': "답변 생성 실패",
                'contexts': [""],
                'ground_truth': item['ground_truth'],
            })
    
    # 답변을 자동으로 JSON 파일에 저장
    save_path = Path(__file__).parent / "generated_answers.json"
    save_data = {
        'config': config.name,
        'results': results,
    }
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print_success(f"답변 저장 완료: {save_path}")
    
    return results


def evaluate_rag_system(results: List[Dict]) -> Dict:
    dataset = Dataset.from_list(results)
    
    # 평가용 LLM 및 Embeddings 설정 (Ragas 호환성)
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    
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
            result_dict = {}
            for col in df.columns:
                if col not in ['user_input', 'retrieved_contexts', 'response', 'reference']:
                    result_dict[col] = df[col].mean()
        except Exception as e:
            print_error(f"점수 추출 실패: {e}")
            result_dict = {}
            for metric in metrics:
                metric_name = metric.name
                if hasattr(eval_result, metric_name):
                    result_dict[metric_name] = getattr(eval_result, metric_name)
        
        return result_dict
    except Exception as e:
        print_error(f"평가 중 오류 발생: {str(e)}")
        raise


def display_results(eval_result: Dict, config_name: str, output_file: str = None):
    print_header(f"📊 평가 결과 - {config_name}")
    
    metrics_dict = eval_result
    
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
        
        if avg_score >= 0.8:
            assessment = f"{Fore.GREEN}우수{Style.RESET_ALL} - RAG 시스템이 매우 잘 작동하고 있습니다!"
        elif avg_score >= 0.6:
            assessment = f"{Fore.YELLOW}양호{Style.RESET_ALL} - 개선의 여지가 있지만 적절하게 작동합니다."
        else:
            assessment = f"{Fore.RED}개선 필요{Style.RESET_ALL} - 시스템 개선이 필요합니다."
        
        print(f"종합 평가: {assessment}\n")
    
    if output_file:
        save_results(metrics_dict, config_name, output_file)


def save_results(results: Dict, config_name: str, output_file: str):
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'config': config_name,
        'metrics': {k: float(v) if isinstance(v, (int, float)) else str(v) 
                   for k, v in results.items()},
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print_success(f"결과 저장 완료: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='RAG 시스템 단일 설정 평가')
    parser.add_argument(
        '--config',
        type=str,
        default='baseline',
        help=f'평가할 설정 이름 (기본값: baseline). 가능한 값: {", ".join([c.name for c in ALL_CONFIGS])}'
    )
    
    args = parser.parse_args()
    
    print_header(f"🔬 RAG 시스템 평가 - {args.config}")
    
    try:
        validate_env()
        print_success("환경 변수 검증 완료")
    except Exception as e:
        print_error(f"환경 변수 검증 실패: {str(e)}")
        sys.exit(1)
    
    # 설정 로드
    try:
        config = get_config(args.config)
        print_success(f"설정 로드: {config}")
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)
    
    base_dir = Path(__file__).parent
    test_dataset_path = base_dir / "test_dataset.json"
    output_path = base_dir / f"evaluation_{args.config}.json"
    
    try:
        # 1. 테스트 데이터셋 로드
        test_data = load_test_dataset(str(test_dataset_path))
        print_success(f"{len(test_data)}개 테스트 케이스 로드")
        
        # 2. RAG 시스템으로 답변 생성
        print_progress("RAG 시스템 답변 생성 중...")
        rag_results = generate_rag_responses(test_data, config)
        
        # 3. Ragas로 평가
        eval_result = evaluate_rag_system(rag_results)
        
        # 4. 결과 출력 및 저장
        display_results(eval_result, args.config, str(output_path))
        
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
