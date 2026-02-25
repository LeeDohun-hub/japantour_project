"""
여러 최적화 버전을 일괄 비교 평가하는 스크립트
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import pandas as pd

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

# 프로젝트 모듈
from src.chain.optimized_rag_chain import prepare_context, generate_answer
from src.config import validate_env
from src.optimization_config import ALL_CONFIGS

# Colorama 초기화
init(autoreset=True)


def print_header(text: str):
    """헤더 출력"""
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}{text:^70}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")


def print_progress(text: str):
    """진행 상태 출력"""
    print(f"{Fore.YELLOW}▶ {text}{Style.RESET_ALL}")


def print_success(text: str):
    """성공 메시지 출력"""
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str):
    """에러 메시지 출력"""
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")


def load_test_dataset(filepath: str) -> List[Dict]:
    """테스트 데이터셋 로드"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def generate_rag_responses_for_config(test_data: List[Dict], config) -> List[Dict]:
    """특정 설정으로 RAG 답변 생성"""
    results = []
    
    desc = f"{config.name} 답변 생성"
    for item in tqdm(test_data, desc=desc, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}'):
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
            print_error(f"질문 처리 실패: {question[:30]}... - {str(e)}")
            results.append({
                'question': question,
                'answer': "답변 생성 실패",
                'contexts': [""],
                'ground_truth': item['ground_truth'],
            })
    
    return results


def evaluate_config(results: List[Dict], config_name: str) -> Dict:
    """특정 설정의 평가"""
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
    
    try:
        eval_result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=eval_llm,
            embeddings=eval_embeddings,
        )
        
        # EvaluationResult에서 점수 추출 - 50개 전체 평균 계산
        try:
            df = eval_result.to_pandas()
            result_dict = {}
            for col in df.columns:
                if col not in ['user_input', 'retrieved_contexts', 'response', 'reference']:
                    result_dict[col] = df[col].mean()
        except Exception as e:
            print_error(f"점수 쵡4출 실패: {e}")
            result_dict = {}
            for metric in metrics:
                metric_name = metric.name
                if hasattr(eval_result, metric_name):
                    result_dict[metric_name] = getattr(eval_result, metric_name)
        
        return result_dict
    except Exception as e:
        print_error(f"{config_name} 평가 실패: {str(e)}")
        return {}


def compare_results(all_results: Dict[str, Dict]):
    """모든 설정의 결과 비교 출력"""
    print_header("📊 전체 비교 결과")
    
    # DataFrame 생성
    df_data = []
    for config_name, metrics in all_results.items():
        if metrics:
            row = {'설정': config_name}
            row.update(metrics)
            df_data.append(row)
    
    if not df_data:
        print_error("비교할 결과가 없습니다.")
        return
    
    df = pd.DataFrame(df_data)
    
    # 설정 컬럼을 인덱스로
    df = df.set_index('설정')
    
    # 평균 점수 계산
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
    df['평균'] = df[numeric_cols].mean(axis=1)
    
    # 정렬 (평균 점수 기준 내림차순)
    df = df.sort_values('평균', ascending=False)
    
    print(f"{Fore.CYAN}【 성능 순위 】{Style.RESET_ALL}\n")
    print(df.to_string())
    print()
    
    # 최고 성능 설정
    best_config = df.index[0]
    best_score = df.loc[best_config, '평균']
    
    print(f"{Fore.GREEN}🏆 최고 성능: {best_config} (평균: {best_score:.4f}){Style.RESET_ALL}\n")
    
    # 개선율 계산 (baseline 대비)
    if 'baseline' in df.index:
        baseline_score = df.loc['baseline', '평균']
        improvement = ((best_score - baseline_score) / baseline_score) * 100
        print(f"{Fore.MAGENTA}📈 Baseline 대비 개선율: {improvement:+.2f}%{Style.RESET_ALL}\n")
    
    return df


def save_comparison_results(all_results: Dict[str, Dict], df: pd.DataFrame, output_dir: Path):
    """비교 결과 저장"""
    # JSON 저장
    json_path = output_dir / "comparison_results.json"
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'results': all_results,
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print_success(f"JSON 결과 저장: {json_path}")
    
    # CSV 저장
    csv_path = output_dir / "comparison_results.csv"
    df.to_csv(csv_path, encoding='utf-8-sig')
    print_success(f"CSV 결과 저장: {csv_path}")


def main():
    """메인 실행 함수"""
    print_header("🔬 RAG 최적화 버전 일괄 비교 평가")
    
    # 환경 변수 검증
    try:
        validate_env()
        print_success("환경 변수 검증 완료")
    except Exception as e:
        print_error(f"환경 변수 검증 실패: {str(e)}")
        sys.exit(1)
    
    # 파일 경로 설정
    base_dir = Path(__file__).parent
    test_dataset_path = base_dir / "test_dataset.json"
    output_dir = base_dir / "evaluation_results"
    output_dir.mkdir(exist_ok=True)
    
    try:
        # 1. 테스트 데이터셋 로드
        print_progress(f"테스트 데이터셋 로드: {test_dataset_path}")
        test_data = load_test_dataset(str(test_dataset_path))
        print_success(f"{len(test_data)}개 테스트 케이스 로드")
        
        # 2. 각 설정별로 평가
        print_header(f"📝 {len(ALL_CONFIGS)}개 설정 평가 시작")
        
        all_results = {}
        
        for i, config in enumerate(ALL_CONFIGS, 1):
            print(f"\n{Fore.MAGENTA}━━━ [{i}/{len(ALL_CONFIGS)}] {config} ━━━{Style.RESET_ALL}\n")
            
            # 답변 생성
            print_progress("답변 생성 중...")
            rag_results = generate_rag_responses_for_config(test_data, config)
            print_success(f"{len(rag_results)}개 답변 생성 완료")
            
            # 평가
            print_progress("Ragas 평가 중...")
            eval_result = evaluate_config(rag_results, config.name)
            
            if eval_result:
                all_results[config.name] = eval_result
                print_success("평가 완료")
                
                # 간단한 결과 출력
                if 'faithfulness' in eval_result:
                    print(f"  Faithfulness: {eval_result['faithfulness']:.4f}")
                if 'answer_relevancy' in eval_result:
                    print(f"  Answer Relevancy: {eval_result['answer_relevancy']:.4f}")
        
        # 3. 비교 결과 출력
        if all_results:
            df = compare_results(all_results)
            
            # 4. 결과 저장
            save_comparison_results(all_results, df, output_dir)
        
        print_header("✅ 모든 평가 완료")
        
    except FileNotFoundError as e:
        print_error(f"파일을 찾을 수 없습니다: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"예상치 못한 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
