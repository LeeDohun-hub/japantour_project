"""
Ragas EvaluationResult 구조 디버깅
"""
import json
from pathlib import Path
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

# 답변 로드
base_dir = Path(__file__).parent
with open(base_dir / "generated_answers.json", 'r', encoding='utf-8') as f:
    data = json.load(f)

results = data['results'][:2]  # 처음 2개만 테스트

# 평가
dataset = Dataset.from_list(results)
eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
eval_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

print("평가 시작...")
eval_result = evaluate(dataset=dataset, metrics=metrics, llm=eval_llm, embeddings=eval_embeddings)

print("\n=== EvaluationResult 타입 ===")
print(type(eval_result))

print("\n=== dir(eval_result) ===")
print([x for x in dir(eval_result) if not x.startswith('_')])

print("\n=== 속성 확인 ===")
for metric in metrics:
    metric_name = metric.name
    print(f"\n{metric_name}:")
    print(f"  hasattr: {hasattr(eval_result, metric_name)}")
    if hasattr(eval_result, metric_name):
        val = getattr(eval_result, metric_name)
        print(f"  value: {val}")
        print(f"  type: {type(val)}")

print("\n=== to_pandas() 시도 ===")
try:
    df = eval_result.to_pandas()
    print(df)
    print("\nColumns:", df.columns.tolist())
except Exception as e:
    print(f"Error: {e}")

print("\n=== vars(eval_result) ===")
try:
    print(vars(eval_result))
except Exception as e:
    print(f"Error: {e}")
