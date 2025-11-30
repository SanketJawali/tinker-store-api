import os

from groq import Groq


class groqClient:
    """
        Class contains all the details related to a conversation.
    """

    client = Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
    )

    history = {}

    def chat(self, role: str, message: str):
        """
            Function to send a message to the llm. Returns the reply object
        """

        res = self.client.chat.completions.create(
            messages=[
                {
                    "role": role,
                    "content": message,
                }
            ],
            model="",
        )

        return res.choices[0].message["content"]
