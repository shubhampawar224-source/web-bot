import logging
import asyncio
from dotenv import load_dotenv

# 👇 LATEST IMPORTS
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.plugins import openai
from livekit.agents import function_tool, RunContext
from typing import Annotated
from openai.types.beta.realtime.session import TurnDetection
from livekit.agents import AgentSession
from voice_config.rag_service import EnhancedRAGAgent

# RAG Import
try:
    from voice_config.rag_service import EnhancedRAGAgent
except ImportError:
    # Fallback
    from rag_service import EnhancedRAGAgent

load_dotenv()

# Initialize RAG
my_rag = EnhancedRAGAgent()

# =======================================================
# 🛠️ TOOL DEFINITION (LATEST STANDARD)
# =======================================================
class RAGFunctions:
    @function_tool(name="consult_knowledge_base", description="Call this tool to find information about the company from the knowledge base.")
    async def consult_knowledge_base(self, context: RunContext, query: str):
        print(f"🔎 LiveKit requesting RAG for: {query}")
        
        # Call RAG logic
        answer = await my_rag.search_and_respond(query)
        
        if "relevant information" in answer or "don't know" in answer:
            return "NO_DATA_FOUND"
            
        print(f"✅ RAG Answer: {answer}")
        return answer

# =======================================================
# 🚀 MAIN AGENT
# =======================================================
async def entrypoint(ctx: JobContext):
    # Room connect
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Tool Initialize
    fnc_ctx = RAGFunctions()

    # 🔥 STRICT INSTRUCTIONS 🔥
    STRICT_PROMPT = """
    You are a voice assistant for TechStart Solutions.
    
    RULES:
    1. You MUST use the 'consult_knowledge_base' tool for every factual question.
    2. If the tool says "NO_DATA_FOUND", apologize and say you don't know.
    3. Do not invent facts.
    4. Keep answers short (under 2 sentences) and speak fast.
    """

    # Model Setup
    model = openai.realtime.RealtimeModel(
        # instructions=STRICT_PROMPT,
        voice="shimmer",
        temperature=0.6,
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.6,          # Noise Gate (0.5 - 0.8 recommended)
            silence_duration_ms=500 # 0.5s Silence = User done speaking
        )
    )

    # Agent Creation
    agent = AgentSession(
        llm=model,
        tools=[fnc_ctx],  # Attach your tool(s) here
    )

    # Start
    await agent.start(ctx)
    
    # Optional Greeting
    await agent.say("System online. Ask me anything.", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


