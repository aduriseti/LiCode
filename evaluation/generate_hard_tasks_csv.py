import json
import urllib.request

import pandas as pd

# The SOTA models and their corresponding latest available folders in the repo
SOTA_MODELS = {
    "Sonnet 4.5": "20251103_sonar-foundation-agent_claude-sonnet-4-5",
    "Opus 4.5": "20251215_livesweagent_claude-opus-4-5",
    "GPT-5": "20251015_Prometheus_v1.2.1_gpt5",
    "Gemini 3": "20251120_livesweagent_gemini-3-pro-preview",
}

BASE_URL = "https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/verified"
GITHUB_WEB_URL = "https://github.com/SWE-bench/experiments/tree/main/evaluation/verified"


def fetch_sota_data(model_folder):
    """Fetches the full results.json for a given model."""
    url = f"{BASE_URL}/{model_folder}/results/results.json"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req) as response:
            if response.getcode() == 200:
                return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def main():
    print("Fetching SOTA data for all 4 frontier models...")
    model_resolved_sets = {}
    all_task_ids = set()
    pass_rates = {}

    for display_name, folder in SOTA_MODELS.items():
        print(f"Fetching {display_name}...")
        data = fetch_sota_data(folder)
        if data:
            resolved = set(data.get("resolved", []))
            model_resolved_sets[display_name] = resolved

            # Reconstruct evaluated set for this model
            evaluated = resolved.union(
                set(data.get("no_generation", [])), set(data.get("no_logs", []))
            )
            all_task_ids.update(evaluated)

            # Calculate pass rate on its evaluated set
            if evaluated:
                pass_rates[display_name] = len(resolved) / len(evaluated)
            else:
                pass_rates[display_name] = 0
        else:
            print(f"Warning: Failed to fetch {display_name}")

    if not all_task_ids:
        print("Error: Could not retrieve any task IDs.")
        return

    # Order models by performance (highest pass rate first = "easiest" model)
    sorted_model_names = sorted(pass_rates.keys(), key=lambda x: pass_rates[x], reverse=True)

    print(f"Analyzing {len(all_task_ids)} total SWE-bench Verified tasks...")

    rows = []
    for task_id in sorted(list(all_task_ids)):
        row = {"Task ID": task_id}
        miss_count = 0
        for name in sorted_model_names:
            if task_id in model_resolved_sets.get(name, set()):
                row[name] = "Pass"
            else:
                row[name] = "Fail"
                miss_count += 1

        row["Miss Count"] = miss_count
        if miss_count > 0:
            rows.append(row)

    # Convert to DataFrame and sort rows by difficulty (increasing Miss Count)
    df = pd.DataFrame(rows)
    df = df.sort_values(by="Miss Count", ascending=True)

    # Reorder columns: Task ID, Miss Count, then Models in sorted order
    cols = ["Task ID", "Miss Count"] + sorted_model_names
    df = df[cols]

    # Create Linked Headers
    linked_headers = {
        name: f"[{name}]({GITHUB_WEB_URL}/{SOTA_MODELS[name]})" for name in sorted_model_names
    }

    final_df = df.rename(columns=linked_headers)

    output_file = "sota_hard_tasks.csv"
    final_df.to_csv(output_file, index=False)

    print(f"\nSuccessfully generated {output_file} with {len(df)} hard tasks.")
    print(f"Models ordered by pass rate: {', '.join(sorted_model_names)}")
    print("\nPreview:")
    # Using to_string for terminal preview as markdown headers are very long
    print(final_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
