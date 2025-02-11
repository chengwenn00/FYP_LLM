# import os
# import openai
# from openai import OpenAI
# from openai import Stream, ChatCompletion

# # GPT3 = "gpt-3.5-turbo-16k"
# # GPT4 = "gpt-4"
# LLAMA3 = "meta-llama/Meta-Llama-3-8B-Instruct"
# DEEPSEEK = "deepseek-r1"

# CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# chat_log_path = os.path.join(CURRENT_DIR, "assets/chat_log.txt")

# class LLMWrapper:
#     def __init__(self, temperature=0.0):
#         self.temperature = temperature
#         self.llama_client = openai.OpenAI(
#             # base_url="http://10.66.41.78:8000/v1",
#             base_url="https://integrate.api.nvidia.com/v1",
#             api_key="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",
#         )
#         self.deepseek_client = openai.OpenAI(
#             base_url="https://integrate.api.nvidia.com/v1",
#             api_key="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",
#         )

#     def request(self, prompt, model_name=LLAMA3, stream=False) -> str | Stream[ChatCompletion.ChatCompletionChunk]:
#         if model_name == LLAMA3:
#             client = self.llama_client
#         else:
#             client = self.deepseek_client
        
#         response = client.chat.completions.create(
#             model=model_name,
#             messages=[{"role": "user", "content": prompt}],
#             temperature=self.temperature,
#             stream=stream,
#         )

#         # save the message in a txt
#         with open(chat_log_path, "a") as f:
#             f.write(prompt + "\n---\n")
#             if not stream:
#                 f.write(response.model_dump_json(indent=2) + "\n---\n")

#         if stream:
#             return response

#         return response.choices[0].message.content
import os
import openai
from openai import OpenAI
from openai import Stream, ChatCompletion

# GPT3 = "gpt-3.5-turbo-16k"
# GPT4 = "gpt-4"
LLAMA3 = "meta-llama/Meta-Llama-3-8B-Instruct"
DEEPSEEK = "deepseek-r1"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
chat_log_path = os.path.join(CURRENT_DIR, "assets/chat_log.txt")

class LLMWrapper:
    def __init__(self, temperature=0.0):
        self.temperature = temperature
        self.llama_client = openai.OpenAI(
            # base_url="http://10.66.41.78:8000/v1",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="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",
        )
        self.deepseek_client = openai.OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="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",
        )

    def request(self, prompt, model_name=LLAMA3, stream=False) -> str | Stream[ChatCompletion.ChatCompletionChunk]:
        if model_name == LLAMA3:
            client = self.llama_client
        else:
            client = self.deepseek_client
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            stream=stream,
        )

        # save the message in a txt
        with open(chat_log_path, "a") as f:
            f.write(prompt + "\n---\n")
            if not stream:
                f.write(response.model_dump_json(indent=2) + "\n---\n")

        if stream:
            return response

        return response.choices[0].message.content