import os
import json
import yfinance as yf
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

# --- ⚡ GROQ + OPENROUTER AI SETUP ---
# LiteLLM/CrewAI automatically uses GROQ_API_KEY for Groq models.
# For OpenRouter models, LiteLLM uses OPENROUTER_API_KEY.

# Set OpenRouter key so LiteLLM can find it
_or_key = os.environ.get("OPENROUTER_API_KEY", "")
if _or_key:
    os.environ["OPENROUTER_API_KEY"] = _or_key

# Full model rotation pool: Groq first, then OpenRouter as overflow
GROQ_MODELS = [
    # --- Groq Models (fast, 8k TPM limit each) ---
    "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3.8-27b",
    "groq/openai/gpt-oss-20b",
    "groq/qwen/qwen3.6-27b",
    "groq/compound",
    "groq/compound-mini",
    "groq/allam-2-7b",
    # --- OpenRouter Free Models (overflow when Groq hits limits) ---
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/nvidia/nemotron-3.5-lightning:free",
    "openrouter/minimax/minimax-m3:free",
    "openrouter/minimax/minimax-m2.7:free",
    "openrouter/google/gemma-4-31b-it:free",
    "openrouter/google/gemma-4-26b-a4b-it:free",
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/meta-llama/llama-3.1-8b-instruct:free",
    "openrouter/mistralai/mistral-7b-instruct:free",
    "openrouter/deepseek/deepseek-r1:free",
    "openrouter/qwen/qwen3-14b:free",
    "openrouter/z-ai/glm-5.2:free",
    "openrouter/thinkingmachines/inkling:free",
    "openrouter/thinkingmachines/inkling-small:free",
    "openrouter/poolside/laguna-s-2.1:free",
    "openrouter/liquid/lfm-2.5-2.6b:free",
]
current_model_idx = 0

def _make_llm(model: str) -> LLM:
    """Create an LLM instance, injecting the correct API key for the provider."""
    if model.startswith("openrouter/"):
        return LLM(model=model, temperature=0.1, api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                   base_url="https://openrouter.ai/api/v1")
    return LLM(model=model, temperature=0.1)

def is_retryable_exception(e) -> bool:
    """Detect if an exception is rate limit, model not found, or temporary API error."""
    err_str = str(e).lower()
    return any(keyword in err_str for keyword in [
        "rate limit", "429", "rate_limit", "limit exceeded", "ratelimit", "too many requests",
        "notfounderror", "model_not_found", "does not exist", "service unavailable", "503",
        "model_decommissioned", "decommissioned"
    ])

groq_llm = _make_llm(GROQ_MODELS[current_model_idx])


# --- 🛠️ TOOLS ---
@tool("live_stock_data_tool")
def live_stock_data_tool(ticker: str) -> str:
    """Fetches live price and volume for a given stock ticker."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        
        if hist.empty:
            return f"Data currently unavailable for {ticker}."
            
        price = hist['Close'].iloc[-1]
        volume = int(hist['Volume'].iloc[-1])
        
        return f"Ticker: {ticker} | Last Price: ${price:.2f} | Volume: {volume}"
    except Exception as e:
        return f"Error fetching data for {ticker}: {e}"

@tool("market_news_tool")
def market_news_tool(ticker: str) -> str:
    """
    Fetches the most recent financial news for a specific stock ticker.
    Use this to check for earnings reports, lawsuits, or major announcements.
    Input MUST be a single valid stock ticker symbol (e.g., 'V', 'MA').
    """
    try:
        import os
        import requests
        api_key = os.getenv("API_TUBE_NEWS_KEY")
        if not api_key:
            return f"Error: API_TUBE_NEWS_KEY not configured. Cannot fetch news for {ticker}."
            
        url = f"https://api.apitube.io/v1/news/everything?q={ticker}&language=en&per_page=5"
        headers = {"X-API-Key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        news_items = response.json().get('results', [])
        
        if not news_items:
            return f"No recent financial news found for {ticker}."

        news_summary = f"--- Recent News for {ticker} ---\n"
        for item in news_items[:5]: 
            title = item.get('title', 'No Title')
            source_info = item.get('source', {})
            publisher = source_info.get('domain', 'Unknown Publisher') if isinstance(source_info, dict) else 'Unknown Publisher'
            link = item.get('href', 'No Link')
            
            news_summary += f"\n📰 **{title}** ({publisher})\n   Link: {link}\n"
            
        return news_summary

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}."

# --- 🤖 AGENTS ---
# The Optimist (legacy; uses Groq like the rest)
bull_analyst = Agent(
    role='Bullish Research Lead',
    goal='Argue FOR the execution of the {ticker_1}/{ticker_2} pair trade.',
    backstory="""You are an expert at identifying mean-reversion opportunities. 
    Your job is to prove that the current Z-score of {z_score} is a massive 
    opportunity and that the spread will inevitably close.""",
    verbose=True,
    allow_delegation=False,
    llm=groq_llm
)

# The Skeptic (legacy; uses Groq like the rest)
bear_analyst = Agent(
    role='Bearish Risk Analyst',
    goal='Argue AGAINST the trade and find "hidden traps".',
    backstory="""You are a cynical veteran trader. You assume every signal is 
    a "Value Trap". Your job is to find news or macro reasons why this pair 
    is diverging for a real reason (e.g., a merger, a lawsuit, or a bankruptcy).""",
    verbose=True,
    allow_delegation=False,
    llm=groq_llm
)
quant_agent = Agent(
    role='Senior Quantitative Analyst',
    goal='Analyze live price and volume data to confirm mean-reversion setups.',
    backstory='You are a master of statistical arbitrage and quantitative finance.',
    verbose=True,
    allow_delegation=False,
    tools=[live_stock_data_tool],
    llm=groq_llm  
)

analyst_agent = Agent(
    role='Head of Fundamental & Sentiment Analysis',
    goal='Check for breaking news, earnings reports, or impending catalysts that could break a correlation.',
    backstory='You are an expert at identifying risk and fundamental shifts in the market.',
    verbose=True,
    allow_delegation=False,
    tools=[market_news_tool],
    llm=groq_llm  
)

bear_analyst_agent = Agent(
    role='Bear Analyst',
    goal='Find concrete reasons NOT to trade the pair: overvaluation, weak volume, negative catalysts, correlation breakdown risks, or unfavorable risk/reward.',
    backstory='You are a skeptical contrarian who always looks for the downside. Your job is to challenge every trade and surface risks others might miss.',
    verbose=True,
    allow_delegation=False,
    tools=[live_stock_data_tool, market_news_tool],
    llm=groq_llm
)

cio_agent = Agent(
    role='Chief Investment Officer',
    goal='Make the final TRADE or SKIP decision by weighing quant data, news summaries, and the Bear Analyst\'s objections. Output strict JSON only.',
    backstory='You are a ruthless hedge fund manager who only takes high-probability mean-reversion trades. You must always consider the Bear Analyst\'s concerns before approving any trade. You output strict JSON.',
    verbose=True,
    allow_delegation=False,
    llm=groq_llm
)

# --- 🚀 SMART EXECUTION ENGINE ---
def evaluate_smart_opportunity(ticker_a, ticker_b=None, technicals=None, quant_context=""):
    """
    Evaluates either a Single Ticker (if ticker_b is None) or a Pair.
    technicals: dict containing {'z_score': x, 'rsi': y, 'type': 'single|pair'}
    quant_context: optional quantitative background context from QuantBrain
    """
    is_pair = ticker_b is not None
    context_str = f"{ticker_a}/{ticker_b}" if is_pair else ticker_a
    type_str = "MEAN-REVERSION PAIR" if is_pair else "SINGLE-TICKER MOMENTUM"
    
    gkey = os.environ.get("GROQ_API_KEY", "")
    gkey_masked = gkey[:6] + "..." + gkey[-4:] if len(gkey) > 10 else "Not Set/Empty"
    print(f"\n📢 Assembling the Crew to evaluate {context_str} ({type_str})")
    print(f"   🔑 Active Groq API Key (Backend Env): {gkey_masked}")

    # 1. Quant Task: Check the math
    quant_desc = (
        f"Check live price/volume for {ticker_a} and {ticker_b}. Current Z-score: {technicals.get('z_score')}. Does the spread support mean-reversion?"
        if is_pair else
        f"Check live price/volume for {ticker_a}. Current RSI: {technicals.get('rsi')}. Is the stock overextended or breaking out?"
    )
    
    # Append any quant brain stats to guide the quant analyst agent
    if quant_context:
        quant_desc += f"\nAdditional Quant Brain Metrics:\n{quant_context}"

    task_quant = Task(
        description=quant_desc,
        expected_output='A quantitative summary confirming if the technical setup is valid.',
        agent=quant_agent
    )

    # 2. Analyst Task: Check the news
    news_desc = (
        f"Check financial news for {ticker_a} and {ticker_b}. Look for catalysts that could break their correlation."
        if is_pair else
        f"Check financial news for {ticker_a}. Is there any reason (earnings, rumors, etc) behind this price movement?"
    )

    task_news = Task(
        description=news_desc,
        expected_output='A fundamental summary of recent catalysts and news sentiment.',
        agent=analyst_agent
    )

    # 3. Bear Task: Try to kill the trade
    bear_desc = (
        f"Find reasons NOT to trade the {ticker_a}/{ticker_b} pair. Look for divergence risk or bankruptcy/lawsuit news."
        if is_pair else
        f"Find reasons NOT to trade {ticker_a}. Is it a pump and dump? Is the RSI divergence fake?"
    )

    task_bear = Task(
        description=bear_desc,
        expected_output='A concise list of skeptical concerns and risks.',
        agent=bear_analyst_agent
    )

    # 4. CIO Task: The Decision
    cio_desc = f"""Review the Quant's math, the Analyst's news, and the Bear's risks for {context_str}.
    Strategy: {type_str}.
    Technicals: {json.dumps(technicals)}
    
    {"Quant Brain Context: " + quant_context if quant_context else ""}

    Decide: BUY, SELL, or WAIT.
    { "BUY/SELL = Open the spread trade" if is_pair else "BUY/SELL = Long/Short the individual stock" }.
    
    Output JSON only:
    {{
        "signal_strength": 0.0 to 1.0,
        "confidence": 0 to 100,
        "strategy_type": "{ "pair" if is_pair else "single" }",
        "bull_case": "...",
        "bear_case": "...",
        "final_action": "BUY/SELL/WAIT"
    }}"""

    task_cio = Task(
        description=cio_desc,
        expected_output='A strict JSON final decision object.',
        agent=cio_agent,
        context=[task_quant, task_news, task_bear]
    )

    global current_model_idx
    max_retries = len(GROQ_MODELS)
    
    for attempt in range(max_retries):
        try:
            print(f"   🤖 Evaluating setup using Groq model: {groq_llm.model} (Attempt {attempt+1}/{max_retries})")
            
            trading_crew = Crew(
                agents=[quant_agent, analyst_agent, bear_analyst_agent, cio_agent],
                tasks=[task_quant, task_news, task_bear, task_cio],
                process=Process.sequential,
                verbose=True
            )
            
            return trading_crew.kickoff()
            
        except Exception as e:
            if is_retryable_exception(e):
                current_model_idx = (current_model_idx + 1) % len(GROQ_MODELS)
                new_model = GROQ_MODELS[current_model_idx]
                print(f"   ⚠️ Model/Rate error on '{groq_llm.model}': {e}")
                print(f"   🔄 Rotating to fallback model: '{new_model}' and retrying immediately...")
                groq_llm = _make_llm(new_model)
                
                # Re-bind agents to use the updated LLM configuration
                for agent in [quant_agent, analyst_agent, bear_analyst_agent, cio_agent]:
                    agent.llm = groq_llm
            else:
                # Raise non-retryable errors immediately
                print(f"   ❌ CrewAI failed with error: {e}")
                raise e
                
    raise Exception("All models in the Groq rotation pool have hit rate limits.")

# Legacy Support
def evaluate_opportunity(sym_a, sym_b, z_score, quant_context=""):
    return evaluate_smart_opportunity(sym_a, sym_b, {"z_score": z_score, "type": "pair"}, quant_context)

# --- 🛡️ TRADE MANAGER ENGINE ---
trade_manager_agent = Agent(
    role='Elite Trade Manager',
    goal='Monitor active open positions, evaluate real-time momentum, news, and technicals, and decide whether to HOLD or CLOSE the position to maximize profits or cut losses.',
    backstory="""You are a ruthless risk manager and elite trader. You do not care about entry prices. You only look at the current chart and news to ask: "If I didn't have this position, would I buy it right now?" If the answer is no, you cut it. You output strict JSON.""",
    verbose=True,
    allow_delegation=False,
    tools=[live_stock_data_tool, market_news_tool],
    llm=groq_llm
)

def evaluate_open_position(ticker, current_pnl, entry_price, quant_context=""):
    """
    Evaluates an existing open position and decides to HOLD or CLOSE.
    """
    gkey = os.environ.get("GROQ_API_KEY", "")
    print(f"\n📢 Assembling the Trade Manager to evaluate OPEN POSITION: {ticker}")
    
    desc = f"""Evaluate the open position for {ticker}.
    Current PnL: ${current_pnl:.2f}
    Entry Price: ${entry_price:.2f}
    
    {"Additional Quant/Market Context: " + quant_context if quant_context else ""}
    
    Analyze the live price, volume, and any breaking news using your tools.
    Decide if the momentum and fundamentals support holding the trade, or if it should be closed to secure profits/cut losses.
    
    Output JSON only:
    {{
        "reason": "...",
        "confidence": 0 to 100,
        "final_action": "HOLD" or "CLOSE"
    }}"""
    
    task_manage = Task(
        description=desc,
        expected_output='A strict JSON final decision object.',
        agent=trade_manager_agent
    )
    
    global current_model_idx
    max_retries = len(GROQ_MODELS)
    
    for attempt in range(max_retries):
        try:
            print(f"   🤖 Evaluating position using Groq model: {groq_llm.model} (Attempt {attempt+1}/{max_retries})")
            
            manager_crew = Crew(
                agents=[trade_manager_agent],
                tasks=[task_manage],
                process=Process.sequential,
                verbose=False
            )
            
            return manager_crew.kickoff()
            
        except Exception as e:
            if is_retryable_exception(e):
                current_model_idx = (current_model_idx + 1) % len(GROQ_MODELS)
                new_model = GROQ_MODELS[current_model_idx]
                print(f"   ⚠️ Model/Rate error on '{groq_llm.model}': {e}")
                print(f"   🔄 Rotating to fallback model: '{new_model}' and retrying immediately...")
                groq_llm = _make_llm(new_model)
                trade_manager_agent.llm = groq_llm
            else:
                print(f"   ❌ CrewAI failed with error: {e}")
                raise e
                
    raise Exception("All models in the Groq rotation pool have hit rate limits.")