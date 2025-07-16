from datetime import datetime
from app.main import read_file, run

def test_run():
    test_file = read_file("./app/user_input/test_1.mdx")
    run(
        [
            "./app/system_prompts/output_instructions.mdx", 
            "./app/system_prompts/polar_reference.mdx", 
            "./app/system_prompts/polar_syntax.mdx",
            "./app/system_prompts/sample_1.polar"
        ],
        test_file,
        "./app/results",
        "test-" + f"{datetime.now()}"
    )

if __name__ == "__main__":
    test_run()
