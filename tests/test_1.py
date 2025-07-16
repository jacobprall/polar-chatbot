from datetime import datetime
from app.main import read_file, run, default_system_prompts

test_prompt_path = "app/user_input/test_1.mdx"

def test_run():
    prompt = read_file(test_prompt_path)
    test_id = datetime.now().isoformat().replace(':', '-').replace('.', '-')
    result_file_name = "test-" + f"{test_id}.polar"
    
    run(
        default_system_prompts,
        prompt,
        "app/results",
        result_file_name
    )

    print("completed test run")


if __name__ == "__main__":
    test_run()
