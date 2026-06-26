"""LLM extraction of NCCI policy narrative into structured JSON rules."""



from __future__ import annotations



import json

import os

import re

from pathlib import Path

from typing import TYPE_CHECKING



from dotenv import load_dotenv

from groq import Groq



load_dotenv()



if TYPE_CHECKING:

    from groq import Groq as GroqClient



DEFAULT_MODEL = "llama-3.3-70b-versatile"

_PLACEHOLDER_API_KEY = "your-groq-api-key-here"





def _groq_api_key_configured() -> bool:

    key = (os.environ.get("GROQ_API_KEY") or "").strip()

    return bool(key) and key != _PLACEHOLDER_API_KEY



# Hardcoded fallback derived from data/ncci_policy_excerpt.txt (28230 / 64450).

SIMULATION_RULES: list[dict] = [

    {

        "column1_code": "28230",

        "column2_code": "64450",

        "modifier_allowed": True,

        "rationale_quote": (

            "if a physician performs a digital block to provide local anesthesia for a "

            "tenotomy of a toe (CPT code 28230), the digital block (CPT code 64450) is "

            "an integral component of the surgical procedure and is not separately reportable."

        ),

    }

]



EXTRACTION_PROMPT = """You are extracting NCCI Procedure-to-Procedure (PTP) bundling rules from policy narrative text.



Read the policy text below and extract every explicit Column 1 / Column 2 code-pair rule you can find.

For each rule, output an object with these fields:

- column1_code: the Column 1 (comprehensive) CPT code as a string

- column2_code: the Column 2 (component) CPT code as a string

- modifier_allowed: boolean — true if an NCCI-associated modifier can bypass the edit

- rationale_quote: a direct verbatim quote from the source text that supports the rule



Return ONLY a JSON array of rule objects. No markdown fences or other commentary.



Policy text:

{policy_text}

"""





def _parse_json_response(raw: str) -> list[dict]:

    text = raw.strip()

    if text.startswith("```"):

        text = re.sub(r"^```(?:json)?\s*", "", text)

        text = re.sub(r"\s*```$", "", text)

    parsed = json.loads(text)

    if isinstance(parsed, dict) and "rules" in parsed:

        return parsed["rules"]

    if isinstance(parsed, list):

        return parsed

    raise ValueError(f"Expected a JSON array of rules, got: {type(parsed).__name__}")





def extract_rules(

    policy_text: str,

    *,

    model: str = DEFAULT_MODEL,

    client: GroqClient | None = None,

) -> list[dict]:

    """Extract structured bundling rules from narrative policy text.



    Uses the Groq API when GROQ_API_KEY is set; otherwise returns

    simulation output grounded in the real 28230/64450 policy excerpt.

    """

    if not _groq_api_key_configured():

        return [dict(rule) for rule in SIMULATION_RULES]



    groq_client = client or Groq(api_key=os.environ.get("GROQ_API_KEY"))

    response = groq_client.chat.completions.create(

        model=model,

        max_tokens=1024,

        messages=[

            {

                "role": "user",

                "content": EXTRACTION_PROMPT.format(policy_text=policy_text),

            }

        ],

    )

    raw = response.choices[0].message.content or ""

    return _parse_json_response(raw)





def load_policy_excerpt(path: Path | str | None = None) -> str:

    """Load the default CMS policy excerpt from data/."""

    if path is None:

        path = Path(__file__).resolve().parent.parent / "data" / "ncci_policy_excerpt.txt"

    return Path(path).read_text(encoding="utf-8")





if __name__ == "__main__":

    policy = load_policy_excerpt()

    mode = "simulation" if not _groq_api_key_configured() else "api"

    print(f"Running extractor ({mode} mode)...")

    rules = extract_rules(policy)

    print(json.dumps(rules, indent=2))

