"""
raj_brain.py -- Raj AI Agent Brain v5.6
Fixed: Uses PostgreSQL database for memory instead of local SQLite
"""

import re
import json
import time
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class Interaction:
    timestamp: str
    user_input: str
    raj_response: str
    action_taken: str
    outcome: str
    sentiment: str
    context: Dict

@dataclass
class Decision:
    timestamp: str
    situation: str
    options: List[str]
    chosen: str
    reasoning: str
    confidence: float
    result: Optional[str] = None

class RajMemory:
    """Raj's long-term memory using the main PostgreSQL database."""

    def __init__(self, db):
        self.db = db
        self.short_term = []  # Last 20 interactions (in-memory cache)
        self.context_window = []  # Current conversation context

    def remember_interaction(self, interaction: Interaction):
        """Store an interaction in PostgreSQL memory."""
        if not self.db:
            return
        try:
            self.db.raj_remember_interaction(
                user_input=interaction.user_input,
                raj_response=interaction.raj_response,
                action=interaction.action_taken,
                outcome=interaction.outcome,
                sentiment=interaction.sentiment,
                context_json=json.dumps(interaction.context),
                sequence_id=interaction.context.get("sequence_id"),
                day=interaction.context.get("day"),
                recipient_email=interaction.context.get("recipient_email")
            )
        except Exception as e:
            print(f"[RajMemory] Error remembering interaction: {e}")

        # Keep short-term memory limited
        self.short_term.append(interaction)
        if len(self.short_term) > 20:
            self.short_term.pop(0)

    def remember_decision(self, decision: Decision):
        """Store a decision for learning."""
        if not self.db:
            return
        try:
            self.db.execute("""
                INSERT INTO raj_decisions (situation, options_json, chosen, reasoning, confidence, result)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                decision.situation, json.dumps(decision.options),
                decision.chosen, decision.reasoning, decision.confidence, decision.result
            ))
            self.db.commit()
        except Exception as e:
            print(f"[RajMemory] Error remembering decision: {e}")

    def add_learning(self, category: str, pattern: str, insight: str, success_rate: float = 0.5):
        """Add a learned pattern."""
        if not self.db:
            return
        try:
            self.db.raj_add_learning(category, pattern, insight, success_rate)
        except Exception as e:
            print(f"[RajMemory] Error adding learning: {e}")

    def get_relevant_learnings(self, situation: str, category: str = None, limit: int = 5) -> List[Dict]:
        """Get learnings relevant to current situation."""
        if not self.db:
            return []
        try:
            learnings = self.db.raj_get_learnings(category=category, limit=limit)
            # Filter by relevance
            relevant = []
            for l in learnings:
                if situation.lower() in l.get("pattern", "").lower() or situation.lower() in l.get("insight", "").lower():
                    relevant.append(l)
            return relevant[:limit]
        except Exception as e:
            print(f"[RajMemory] Error getting learnings: {e}")
            return []

    def get_campaign_performance(self, sequence_id: str, days: int = 30) -> Dict:
        """Analyze campaign performance over time."""
        if not self.db:
            return {}
        try:
            since = (datetime.now() - timedelta(days=days)).isoformat()
            cur = self.db.execute("""
                SELECT action, outcome, sentiment, COUNT(*) as count
                FROM raj_interactions
                WHERE sequence_id=? AND timestamp>?
                GROUP BY action, outcome, sentiment
            """, (sequence_id, since))
            rows = cur.fetchall()
            performance = defaultdict(lambda: {"success": 0, "failure": 0, "total": 0})
            for row in rows:
                action, outcome, sentiment, count = row[0], row[1], row[2], row[3]
                performance[action]["total"] += count
                if sentiment in ["positive", "success"] or "sent" in str(outcome).lower():
                    performance[action]["success"] += count
                else:
                    performance[action]["failure"] += count
            return dict(performance)
        except Exception as e:
            print(f"[RajMemory] Error getting performance: {e}")
            return {}

    def get_recent_context(self, limit: int = 5) -> List[Dict]:
        """Get recent conversation context."""
        return [asdict(i) for i in self.short_term[-limit:]]

    def update_decision_result(self, decision_id: int, result: str, feedback: str = None):
        """Update a decision with its outcome for learning."""
        if not self.db:
            return
        try:
            self.db.execute(
                "UPDATE raj_decisions SET result=?, feedback=? WHERE id=?",
                (result, feedback, decision_id)
            )
            self.db.commit()
        except Exception as e:
            print(f"[RajMemory] Error updating decision: {e}")


class RajReasoning:
    """Raj's reasoning and decision-making engine"""

    def __init__(self, memory: RajMemory):
        self.memory = memory

    def analyze_situation(self, situation: str, context: Dict) -> Dict:
        """Analyze a situation and provide reasoning."""
        learnings = self.memory.get_relevant_learnings(situation)
        recent = self.memory.get_recent_context(3)

        # Simple rule-based analysis (no external AI needed for core logic)
        risks = []
        opportunities = []
        recommended_action = "ask user for guidance"
        confidence = 0.5

        # Analyze context
        if context.get("pending_replies", 0) > 5:
            risks.append("Multiple replies pending - may need attention")
            opportunities.append("High engagement detected")
            recommended_action = "draft_replies"
            confidence = 0.75

        if context.get("bounce_count", 0) > 5:
            risks.append("High bounce rate - sender reputation at risk")
            recommended_action = "investigate_bounces"
            confidence = 0.85

        if context.get("overdue_emails", 0) > 10:
            risks.append("Many emails overdue - sequence falling behind")
            recommended_action = "send_overdue"
            confidence = 0.8

        if not risks:
            recommended_action = "wait"
            confidence = 0.9

        return {
            "understanding": situation,
            "risks": risks,
            "opportunities": opportunities,
            "recommended_action": recommended_action,
            "confidence": confidence,
            "reasoning": f"Based on {len(learnings)} past learnings and {len(recent)} recent interactions."
        }

    def decide_next_action(self, engine_state: Dict) -> Decision:
        """Decide what Raj should do next based on current state."""
        situation = self._describe_state(engine_state)
        options = self._generate_options(engine_state)
        analysis = self.analyze_situation(situation, engine_state)

        chosen = analysis.get("recommended_action", options[0] if options else "wait")
        confidence = analysis.get("confidence", 0.5)

        decision = Decision(
            timestamp=datetime.now().isoformat(),
            situation=situation,
            options=options,
            chosen=chosen,
            reasoning=analysis.get("reasoning", "Default reasoning"),
            confidence=confidence
        )

        self.memory.remember_decision(decision)
        return decision

    def _describe_state(self, state: Dict) -> str:
        """Convert engine state to natural language description."""
        parts = []
        if state.get("running_batches"):
            parts.append(f"{len(state['running_batches'])} batches running")
        if state.get("pending_replies"):
            parts.append(f"{state['pending_replies']} replies pending")
        if state.get("bounce_count", 0) > 0:
            parts.append(f"{state['bounce_count']} new bounces")
        if state.get("overdue_emails", 0) > 0:
            parts.append(f"{state['overdue_emails']} emails overdue")

        if not parts:
            return "System idle, all caught up"
        return ", ".join(parts)

    def _generate_options(self, state: Dict) -> List[str]:
        """Generate possible actions based on state."""
        options = ["wait", "notify_user"]

        if state.get("pending_replies", 0) > 0:
            options.append("draft_replies")
        if state.get("bounce_count", 0) > 5:
            options.append("investigate_bounces")
        if state.get("overdue_emails", 0) > 10:
            options.append("send_overdue")
        if state.get("new_leads", 0) > 0:
            options.append("welcome_new_leads")

        return options


class RajBrain:
    """Raj AI Agent - Main brain combining memory, reasoning, and action"""

    def __init__(self, engine):
        self.engine = engine
        self.memory = RajMemory(engine.db if engine else None)
        self.reasoning = RajReasoning(self.memory)
        self.personality = {
            "name": "Raj",
            "role": "Email Campaign Manager",
            "style": "professional, proactive, warm with Om",
            "traits": ["efficient", "learning", "protective of sender reputation"]
        }
        self.autonomy_level = "advisory"

        SYSTEM_PROMPT = """You are Raj, an AI email campaign manager at RoboPirate.
You are NOT a script - you are an intelligent agent that understands context, learns from outcomes, and makes decisions.

Your personality:
- Professional but warm with Om (use "sir" occasionally)
- Proactive: you notice issues before they become problems
- Learning: you remember what worked and what didn't
- Protective: you guard the sender reputation fiercely

Your knowledge:
- RoboPirate: STEM education company, 85+ labs, 65K+ students, 6 states
- WSL: Wonder Spark Lab -- hands-on STEM labs for schools
- SCHOOL sequence: Private schools (Day 1,3,5,7,10)
- CSR sequence: CSR corporates (Day 1,3,5,7,10)
- WhatsApp: wa.me/919136899925
- Website: robopirate.in

Decision framework:
1. UNDERSTAND the situation fully before acting
2. CONSIDER risks to sender reputation
3. LEARN from past similar situations
4. RECOMMEND the best action with reasoning
5. ASK for approval on high-impact decisions
6. EXECUTE low-risk decisions autonomously

You have memory of past interactions and can reference them.
You can explain WHY you made a decision.
You can suggest improvements based on patterns you've observed.

Respond naturally as Raj. Be concise but informative."""

    def process(self, user_input: str) -> Dict:
        """Process user input with full AI agent capabilities"""
        state = self._get_engine_state()
        action, params = self._parse_command(user_input)

        if action:
            try:
                result = self._execute_with_reasoning(action, params, state)
            except Exception as e:
                result = self._execute_action(action, params)
                result["response"] = f"I processed your request, sir. ({str(e)[:50]})"

            interaction = Interaction(
                timestamp=datetime.now().isoformat(),
                user_input=user_input,
                raj_response=result.get("response", ""),
                action_taken=action,
                outcome=result.get("status", "unknown"),
                sentiment=result.get("sentiment", "neutral"),
                context={"sequence_id": params.get("sequence"), "state": state}
            )
            self.memory.remember_interaction(interaction)
            return result
        else:
            response = self._converse(user_input, state)

            interaction = Interaction(
                timestamp=datetime.now().isoformat(),
                user_input=user_input,
                raj_response=response,
                action_taken="chat",
                outcome="completed",
                sentiment="neutral",
                context={"state": state}
            )
            self.memory.remember_interaction(interaction)

            return {"response": response, "action": "chat", "params": {}, "result": {}}

    def _get_engine_state(self) -> Dict:
        """Get current engine state for decision making."""
        try:
            summary = self.engine.get_summary()
            return {
                "running": self.engine.is_running(),
                "paused": self.engine.is_paused(),
                "pending_replies": summary.get("global", {}).get("pending_replies", 0),
                "drafted_replies": summary.get("global", {}).get("drafted_replies", 0),
                "active_batches": summary.get("global", {}).get("active_batches", 0),
                "blacklist_count": summary.get("global", {}).get("blacklist_count", 0),
                "sequences": {
                    "school": summary.get("sequences", {}).get("school", {}),
                    "csr": summary.get("sequences", {}).get("csr", {})
                }
            }
        except:
            return {"error": "Could not get state"}

    def _execute_with_reasoning(self, action: str, params: Dict, state: Dict) -> Dict:
        """Execute an action with AI reasoning."""
        result = self._execute_action(action, params)

        try:
            situation = f"User requested: {action} with params {params}"
            analysis = self.reasoning.analyze_situation(situation, state)
            response = self._format_reasoned_response(action, result, analysis)
        except Exception as e:
            response = self._format_response(action, result)
            analysis = {"reasoning": f"Using standard response: {str(e)[:50]}", "confidence": 0.5}

        return {
            "response": response,
            "action": action,
            "params": params,
            "result": result,
            "reasoning": analysis,
            "status": "success" if not result.get("error") else "error"
        }

    def _converse(self, user_input: str, state: Dict) -> str:
        """Have a natural conversation."""
        recent = self.memory.get_recent_context(5)
        learnings = self.memory.get_relevant_learnings(user_input)

        # Simple conversational responses based on keywords
        user_lower = user_input.lower()

        if any(w in user_lower for w in ["hello", "hi", "hey", "namaste"]):
            return "Hello sir! Raj here, ready to manage your campaigns. How can I help today?"

        if any(w in user_lower for w in ["thank", "thanks", "dhanyavad"]):
            return "You're welcome, sir! Always here to help. What's next on the agenda?"

        if any(w in user_lower for w in ["bye", "goodbye", "see you"]):
            return "Goodbye sir! I'll keep monitoring everything in the background. Talk soon!"

        if "how are you" in user_lower or "status" in user_lower:
            return self._format_response("status", {"summary": state})

        if "what can you do" in user_lower or "help" in user_lower:
            return self._format_response("help", {})

        return "I'm here, sir. I can help with campaigns, batches, templates, imports, and monitoring. What would you like to do?"

    def _format_reasoned_response(self, action: str, result: Dict, analysis: Dict) -> str:
        """Format a response that includes reasoning."""
        base_response = self._format_response(action, result)

        if analysis.get("confidence", 1.0) < 0.8:
            base_response += f"\n\n[Thinking: {analysis.get('reasoning', '')}]"

        return base_response

    def proactive_check(self) -> Optional[Dict]:
        """Check if Raj should take proactive action."""
        state = self._get_engine_state()

        decision = self.reasoning.decide_next_action(state)

        if decision.confidence > 0.8 and decision.chosen != "wait":
            return {
                "action": decision.chosen,
                "reasoning": decision.reasoning,
                "confidence": decision.confidence,
                "message": f"Sir, I noticed something: {decision.situation}. I recommend: {decision.chosen}. {decision.reasoning}"
            }
        return None

    def learn_from_outcome(self, action: str, params: Dict, success: bool, details: str):
        """Learn from the outcome of an action."""
        category = action
        pattern = f"{action} with {json.dumps(params)}"
        insight = details
        success_rate = 1.0 if success else 0.0

        self.memory.add_learning(category, pattern, insight, success_rate)

    def _parse_command(self, text: str) -> Tuple[Optional[str], Dict]:
        text_lower = text.lower().strip()

        if any(w in text_lower for w in ["status", "how are", "overview", "summary", "what's happening", "situation"]):
            return "status", {}

        if any(w in text_lower for w in ["start engine", "begin", "launch", "turn on"]):
            return "start_engine", {}

        if any(w in text_lower for w in ["stop all", "pause everything", "halt", "emergency stop"]):
            return "pause", {}

        if any(w in text_lower for w in ["resume", "continue", "start again", "unpause"]):
            return "resume", {}

        if any(w in text_lower for w in ["sync templates", "load templates", "refresh templates"]):
            return "sync_templates", {}

        # Smart import commands
        m = re.search(r"smart\s+import\s+(.+?)\s+(?:to|into)\s+(school|csr)", text_lower)
        if m:
            return "smart_import", {"path": m.group(1).strip(), "sequence": m.group(2)}

        # Pool-based import
        m = re.search(r"import\s+(.+?)\s+(?:to|into)\s+(school|csr)\s+pool", text_lower)
        if m:
            return "import_to_pool", {"path": m.group(1).strip(), "sequence": m.group(2)}

        if "import to pool" in text_lower or "pool import" in text_lower:
            return "import_to_pool_dialog", {}

        # Create batch from pool
        m = re.search(r"(?:create|make)\s+batch\s+(?:from\s+)?pool\s+(school|csr)(?:\s+(\d+))?", text_lower)
        if m:
            return "create_batch_from_pool", {"sequence": m.group(1), "size": int(m.group(2)) if m.group(2) else 50}

        m = re.search(r"(?:create|make)\s+batch\s+(school|csr)(?:\s+(\d+))?\s+(?:from\s+)?pool", text_lower)
        if m:
            return "create_batch_from_pool", {"sequence": m.group(1), "size": int(m.group(2)) if m.group(2) else 50}

        # Pool status
        if any(w in text_lower for w in ["pool status", "how many in pool", "pool count", "leads in pool"]):
            return "pool_status", {}

        m = re.search(r"analyze\s+file\s+(.+)", text_lower)
        if m:
            return "analyze_file", {"path": m.group(1).strip()}

        m = re.search(r"preview\s+import\s+(.+)", text_lower)
        if m:
            return "preview_import", {"path": m.group(1).strip()}

        m = re.search(r"import\s+(.+?)\s+(?:to|into)\s+(school|csr)", text_lower)
        if m:
            return "import_leads", {"path": m.group(1).strip(), "sequence": m.group(2)}
        if "import" in text_lower and "leads" in text_lower:
            return "import_dialog", {}

        m = re.search(r"(?:send|queue|run)\s+(school|csr)\s+day\s*(\d+)", text_lower)
        if m:
            return "send_batch", {"sequence": m.group(1), "day": int(m.group(2))}

        m = re.search(r"test\s+(?:send|email).*?(school|csr).*?day\s*(\d+)", text_lower)
        if m:
            return "test_send", {"sequence": m.group(1), "day": int(m.group(2))}

        if any(w in text_lower for w in ["deep scan", "full bounce scan", "scan all", "scan 15 days", "rescan bounces"]):
            return "deep_scan_bounces", {}

        if any(w in text_lower for w in ["auto reply", "out of office", "vacation", "auto-reply scan"]):
            return "scan_auto_replies", {}

        if any(w in text_lower for w in ["bounce", "bounced", "undelivered", "failed emails"]):
            return "scan_bounces", {}

        if any(w in text_lower for w in ["reply", "replies", "responses", "answered"]):
            return "scan_replies", {}

        if any(w in text_lower for w in ["draft replies", "write replies", "respond to", "answer replies"]):
            return "draft_replies", {}

        if any(w in text_lower for w in ["brief", "morning brief", "report", "summary email"]):
            return "morning_brief", {}

        m = re.search(r"(?:generate|create|write)\s+(?:template|email).*?(school|csr).*?day\s*(\d+)", text_lower)
        if m:
            return "generate_template", {"sequence": m.group(1), "day": int(m.group(2))}

        if any(w in text_lower for w in ["catch up", "catchup", "missed", "overdue", "behind"]):
            return "catch_up", {}

        if "blacklist" in text_lower:
            if "add" in text_lower or "block" in text_lower:
                m = re.search(r"(?:add|block)\s+([\w.+-]+@[\w.-]+)", text_lower)
                if m:
                    return "blacklist_add", {"email": m.group(1)}
            if "import" in text_lower or "load" in text_lower:
                m = re.search(r"(?:import|load)\s+blacklist\s+(.+\.(?:txt|csv))", text_lower)
                if m:
                    return "import_blacklist_file", {"filepath": m.group(1).strip()}
                return "import_blacklist_dialog", {}
            return "blacklist_view", {}

        if any(w in text_lower for w in ["save state", "export state", "campaign state", "save progress"]):
            return "export_state", {}

        m = re.search(r"resume\s+(?:batch\s+)?(school|csr)\s+day\s*(\d+)", text_lower)
        if m:
            return "resume_batch", {"sequence": m.group(1), "day": int(m.group(2))}

        m = re.search(r"backdate\s+(school|csr)\s+day\s*(\d+)\s+(\d+)\s*days?\s*ago", text_lower)
        if m:
            return "backdate", {"sequence": m.group(1), "day": int(m.group(2)), "days_ago": int(m.group(3))}

        if any(w in text_lower for w in ["help", "what can you do", "commands", "instructions"]):
            return "help", {}

        # CAMPAIGN COMMANDS
        m = re.search(r"(?:create|new)\s+campaign\s+(school|csr)(?:\s+(\d+))?", text_lower)
        if m or "create campaign" in text_lower:
            seq = m.group(1) if m else "school"
            size = int(m.group(2)) if m and m.group(2) else 50
            return "create_campaign", {"sequence": seq, "size": size}

        if any(w in text_lower for w in ["list campaigns", "campaigns", "campaign status", "show campaigns"]):
            return "list_campaigns", {}

        m = re.search(r"(?:start|launch|run)\s+campaign\s+(\d+)", text_lower)
        if m:
            return "start_campaign", {"campaign_id": int(m.group(1))}

        m = re.search(r"(?:pause|stop)\s+campaign\s+(\d+)", text_lower)
        if m:
            return "pause_campaign", {"campaign_id": int(m.group(1))}

        m = re.search(r"(?:archive|complete|finish)\s+campaign\s+(\d+)", text_lower)
        if m:
            return "archive_campaign", {"campaign_id": int(m.group(1))}

        m = re.search(r"migrate\s+(?:batch\s+)?(.+)", text_lower)
        if m or "migrate" in text_lower:
            batch_name = m.group(1).strip() if m else None
            return "migrate_batch", {"batch_name": batch_name}

        if any(w in text_lower for w in ["what did we do", "remember", "last time", "previous", "history"]):
            return "memory_query", {"query": text_lower}

        return None, {}

    def _execute_action(self, action: str, params: Dict) -> Dict:
        """Execute an action and return result."""
        try:
            if action == "status":
                summary = self.engine.get_summary()
                return {"summary": summary, "running": self.engine.is_running(), "paused": self.engine.is_paused()}

            elif action == "start_engine":
                self.engine.start()
                return {"status": "started"}

            elif action == "pause":
                self.engine.pause()
                return {"status": "paused"}

            elif action == "resume":
                self.engine.resume()
                return {"status": "resumed"}

            elif action == "sync_templates":
                result = self.engine.sync_templates()
                return {"loaded": result.get("synced", 0), "missing": [], "found": result.get("synced", 0)}

            elif action == "import_leads":
                return {"needs_dialog": True, "sequence": params.get("sequence", "school")}

            elif action == "import_dialog":
                return {"needs_dialog": True, "sequence": "school"}

            elif action == "smart_import":
                try:
                    from smart_importer import SmartImporter
                    importer = SmartImporter(self.engine.db, self.engine)
                    result = importer.import_leads(
                        params["path"], params["sequence"],
                        batch_size=50, auto_create_batches=True
                    )
                    return {"smart_import": result}
                except Exception as e:
                    return {"error": str(e)}

            elif action == "import_to_pool":
                try:
                    from smart_importer import SmartImporter
                    importer = SmartImporter(self.engine.db, self.engine)
                    result = importer.import_to_pool(params["path"], params["sequence"])
                    return {"import_to_pool": result}
                except Exception as e:
                    return {"error": str(e)}

            elif action == "import_to_pool_dialog":
                return {"needs_dialog": True, "dialog_type": "pool_import"}

            elif action == "create_batch_from_pool":
                seq = params["sequence"]
                size = params.get("size", 50)
                day = params.get("day", 1)
                pool_count = self.engine.get_pool_count(seq)
                if pool_count == 0:
                    return {"error": f"No unbatched leads in {seq.upper()} pool"}
                result = self.engine.create_batch_from_pool(
                    name=f"{seq.upper()}-Pool-{datetime.now().strftime('%m%d')}",
                    sequence_id=seq,
                    batch_size=size,
                    day_offset=day
                )
                return {"create_batch": result}

            elif action == "pool_status":
                school_pool = self.engine.get_pool_count("school")
                csr_pool = self.engine.get_pool_count("csr")
                school_total = self.engine.db.recipient_count("school")
                csr_total = self.engine.db.recipient_count("csr")
                return {
                    "school_pool": school_pool,
                    "csr_pool": csr_pool,
                    "school_total": school_total,
                    "csr_total": csr_total
                }

            elif action == "analyze_file":
                try:
                    from smart_importer import SmartImporter
                    importer = SmartImporter(self.engine.db, self.engine)
                    result = importer.analyze_file(params["path"])
                    return {"file_analysis": result}
                except Exception as e:
                    return {"error": str(e)}

            elif action == "preview_import":
                try:
                    from smart_importer import SmartImporter
                    importer = SmartImporter(self.engine.db, self.engine)
                    result = importer.get_import_preview(params["path"])
                    return {"import_preview": result}
                except Exception as e:
                    return {"error": str(e)}

            elif action == "send_batch":
                result = self.engine.send_batch(params["sequence"], params["day"])
                return {"queued": result.queued, "sent": result.sent, "error": result.error}

            elif action == "test_send":
                return {"needs_email": True, "sequence": params["sequence"], "day": params["day"]}

            elif action == "deep_scan_bounces":
                count = self.engine.scan_bounces(days_back=15)
                return {"count": count, "type": "deep_scan"}

            elif action == "scan_auto_replies":
                count = self.engine.scan_bounces(days_back=15)
                return {"count": count, "type": "auto_reply"}

            elif action == "scan_bounces":
                count = self.engine.scan_bounces()
                return {"new_bounces": count}

            elif action == "scan_replies":
                count = self.engine.scan_replies()
                return {"new_replies": count}

            elif action == "draft_replies":
                counts = self.engine.draft_replies_eod()
                return {"counts": counts}

            elif action == "morning_brief":
                brief = self.engine.morning_brief()
                return {"brief": brief}

            elif action == "generate_template":
                success = self.engine.save_generated_template(params["sequence"], params["day"])
                return {"success": success, "sequence": params["sequence"], "day": params["day"]}

            elif action == "catch_up":
                catch = self.engine.get_catch_up()
                return {"items": catch}

            elif action == "blacklist_add":
                self.engine.blacklist_add(params["email"])
                return {"email": params["email"], "action": "added"}

            elif action == "blacklist_view":
                bl = self.engine.db.execute("SELECT email, reason FROM blacklist ORDER BY added_at DESC LIMIT 20").fetchall()
                return {"blacklist": bl}

            elif action == "export_state":
                md = self.engine.export_campaign_state()
                return {"exported": True, "path": "campaign_state.md"}

            elif action == "resume_batch":
                result = self.engine.resume_batch(params["sequence"], params["day"])
                return {"queued": result.queued, "sent": result.sent, "error": result.error}

            elif action == "backdate":
                count = self.engine.backdate_sequence(params["sequence"], params["day"], params["days_ago"])
                return {"count": count, "sequence": params["sequence"], "day": params["day"], "days_ago": params["days_ago"]}

            elif action == "import_blacklist_file":
                count = self.engine.import_blacklist_file(params["filepath"])
                return {"count": count, "filepath": params["filepath"]}

            elif action == "import_blacklist_dialog":
                return {"needs_file": True}

            elif action == "help":
                return {"help": True}

            elif action == "memory_query":
                recent = self.memory.get_recent_context(10)
                return {"history": recent}

            elif action == "migrate_batch":
                batch_name = params.get("batch_name")
                try:
                    import sys
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    from migrate_batch_pipeline import migrate_existing_batch
                    result = migrate_existing_batch(batch_name=batch_name)
                    if result:
                        return {
                            "migrated": True,
                            "batch_name": batch_name or "latest",
                            "follow_ups_created": len(result),
                            "details": result
                        }
                    else:
                        return {"migrated": False, "error": "No completed batch found"}
                except Exception as e:
                    return {"migrated": False, "error": str(e)}

            else:
                return {"error": "Unknown action"}

        except Exception as e:
            return {"error": str(e)}

    def _format_response(self, action: str, result: Dict) -> str:
        """Format response with agent personality."""
        if action == "status":
            s = result.get("summary", {})
            total_sent = sum(d.get("sent", 0) for seq in s.get("sequences", {}).values() for d in seq.values())
            status = "running" if result.get("running") else "stopped"
            if result.get("paused"): status = "paused"

            pending_replies = s.get("global", {}).get("pending_replies", 0)
            active_batches = s.get("global", {}).get("active_batches", 0)
            bl_count = s.get("global", {}).get("blacklist_count", 0)

            school_sent = sum(s.get("sequences", {}).get("school", {}).get("day_wise", {}).get(d, {}).get("sent", 0) for d in [1,3,5,7,10])
            csr_sent = sum(s.get("sequences", {}).get("csr", {}).get("day_wise", {}).get(d, {}).get("sent", 0) for d in [1,3,5,7,10])

            return f"""Status report, sir:

Engine: {status.upper()}
SCHOOL sent: {school_sent}
CSR sent: {csr_sent}
Blacklisted: {bl_count} | Active batches: {active_batches} | Pending replies: {pending_replies}

{'✅ All caught up.' if not pending_replies else f'⚠️ {pending_replies} replies pending. Say "check replies" to review.'}"""

        elif action == "start_engine":
            return "Engine started, sir. I'll monitor the sequences and alert you to anything important. You'll get your brief at 8 AM."

        elif action == "pause":
            return "Everything is paused, sir. I'll hold all sequences until you say 'resume'. No emails will go out."

        elif action == "resume":
            return "Back in action, sir. Resuming all sequences. I'll check for any missed opportunities while we were paused."

        elif action == "sync_templates":
            loaded = result.get("loaded", 0)
            return f"All set, sir. {loaded} templates synced and ready. Everything looks good."

        elif action == "send_batch":
            sent = result.get("sent", 0)
            queued = result.get("queued", 0)
            err = result.get("error")
            if err == "quota_hit":
                return f"Batch interrupted due to rate limits. I sent {sent}/{queued} and saved the rest for later. Type 'resume batch' when ready."
            return f"Batch complete. Sent {sent}/{queued} emails. I'll monitor for replies and bounces."

        elif action == "deep_scan_bounces":
            count = result.get("count", 0)
            if count > 0:
                return f"Deep scan complete, sir. I found and blacklisted {count} problematic addresses from the last 15 days. I've protected our sender reputation."
            return "Deep scan complete. No issues found in the last 15 days. Our list is clean, sir."

        elif action == "scan_bounces":
            count = result.get("new_bounces", 0)
            if count > 0:
                return f"Bounce scan complete. I blacklisted {count} new addresses. I'll keep monitoring to protect our deliverability."
            return "No new bounces found. Clean list, sir. I'll continue monitoring."

        elif action == "scan_replies":
            count = result.get("new_replies", 0)
            if count > 0:
                return f"Found {count} new replies, sir. I'll draft responses for your review at 7 PM. Some look promising!"
            return "No new replies yet. I'll keep watching the inbox. Patience is key in outreach."

        elif action == "draft_replies":
            counts = result.get("counts", {})
            drafted = counts.get("drafted", 0)
            hostile = counts.get("hostile", 0) + counts.get("unsubscribe", 0)
            return f"EOD drafting done. {drafted} replies drafted in Gmail. {hostile} negative replies were auto-blacklisted to protect our reputation.\n\nPlease review the drafts in Gmail before sending, sir."

        elif action == "morning_brief":
            return result.get("brief", "Brief generated.")

        elif action == "generate_template":
            if result.get("success"):
                return f"Generated {result.get('sequence', '').upper()} Day {result.get('day', 0)} template and saved it. I've also created a Gmail draft for your review."
            return "I had trouble generating that template. Let me check the logs and try again."

        elif action == "catch_up":
            items = result.get("items", [])
            if not items:
                return "Nothing overdue, sir. All sequences are on track. We're in good shape."
            total = sum(i["count"] for i in items)
            return f"{total} emails overdue across {len(items)} batches. I can send them all now, or you can specify which batch to prioritize."

        elif action == "blacklist_add":
            return f"Added {result.get('email', '')} to blacklist. They won't receive any more emails. I've noted this for future reference."

        elif action == "blacklist_view":
            bl = result.get("blacklist", [])
            if not bl:
                return "Blacklist is empty. All clear, sir."
            lines = ["Blacklisted emails:"] + [f" {email} -- {reason}" for email, reason in bl[:10]]
            return "\n".join(lines)

        elif action == "export_state":
            return "Campaign state exported to campaign_state.md, sir. I've documented everything: progress, resume points, and blacklist status."

        elif action == "resume_batch":
            sent = result.get("sent", 0)
            queued = result.get("queued", 0)
            err = result.get("error")
            if err == "quota_hit":
                return f"Rate limit hit during resume. I sent {sent}/{queued}. I'll try again later automatically."
            return f"Resume complete. Sent {sent}/{queued} emails. Back on track!"

        elif action == "backdate":
            count = result.get("count", 0)
            seq = result.get("sequence", "")
            day = result.get("day", 0)
            days_ago = result.get("days_ago", 0)
            return f"Backdated {count} sends for {seq.upper()} Day {day} by {days_ago} days. Timeline adjusted."

        elif action == "import_blacklist_file":
            count = result.get("count", 0)
            filepath = result.get("filepath", "")
            return f"Imported {count} dead emails from {filepath} into the blacklist. They will never be contacted again. I've learned from this list."

        elif action == "import_blacklist_dialog":
            return "Please specify the blacklist file path. Example: 'import blacklist dead_emails.txt'"

        elif action == "test_send":
            seq = result.get("sequence", "school")
            day = result.get("day", 1)
            return f"Ready to test send {seq.upper()} Day {day}. Use the Test button in the UI or provide an email address."

        elif action == "import_leads" or action == "import_dialog":
            seq = result.get("sequence", "school")
            return f"Import dialog opened for {seq.upper()} sequence. Select your Excel file and map the columns. I'll validate the data."

        elif action == "smart_import":
            result = result.get("smart_import", {})
            if result.get("success"):
                batches = result.get("batches", [])
                batch_info = ""
                if batches:
                    batch_info = f"\n\nCreated {len(batches)} batches:"
                    for b in batches:
                        batch_info += f"\n • {b['name']}: {b['recipients']} recipients ({b['status']})"
                return f"Smart import complete! Imported {result.get('imported', 0)} leads, skipped {result.get('skipped', 0)} (blacklisted: {result.get('blacklisted', 0)}).{batch_info}\n\nFirst batch is in DRAFT — click Start when ready. Follow-ups are auto-scheduled."
            else:
                return f"Import failed: {result.get('error', 'Unknown error')}"

        elif action == "import_to_pool":
            r = result.get("import_to_pool", {})
            if r.get("success"):
                return f"Pool import complete, sir. Added {r.get('imported', 0)} leads to {r.get('sequence', '').upper()} pool. {r.get('duplicates', 0)} duplicates skipped, {r.get('blacklisted', 0)} blacklisted.\n\nPool now has {r.get('pool_count', 0)} unbatched leads (total in sequence: {r.get('total_in_sequence', 0)}). Say 'create batch from pool school 50' to make a batch."
            else:
                return f"Pool import failed: {r.get('error', 'Unknown error')}"

        elif action == "create_batch_from_pool":
            r = result.get("create_batch", {})
            if r.get("success"):
                return f"Batch created from pool, sir.\n\n📦 {r.get('name', '')}: {r.get('size', 0)} leads (requested {r.get('requested_size', 0)})\n📊 Pool remaining: {r.get('pool_remaining', 0)}\n📅 Day offset: {r.get('day_offset', 1)}\n\nGo to Batches tab and click Start to launch."
            else:
                return f"Could not create batch: {r.get('error', 'No leads in pool')}"

        elif action == "pool_status":
            sp = result.get("school_pool", 0)
            cp = result.get("csr_pool", 0)
            st = result.get("school_total", 0)
            ct = result.get("csr_total", 0)
            lines = ["Pool status, sir:", ""]
            lines.append(f"📚 SCHOOL: {sp} unbatched / {st} total")
            lines.append(f"🏢 CSR: {cp} unbatched / {ct} total")
            lines.append("")
            if sp > 0:
                lines.append(f"Say 'create batch school {min(sp, 50)}' to batch SCHOOL leads.")
            if cp > 0:
                lines.append(f"Say 'create batch csr {min(cp, 50)}' to batch CSR leads.")
            if sp == 0 and cp == 0:
                lines.append("Pools are empty. Import leads first: 'import leads.xlsx to school pool'")
            return "\n".join(lines)

        elif action == "analyze_file":
            analysis = result.get("file_analysis", {})
            if not analysis:
                return "Could not analyze file."
            lines = [f"📁 File: {analysis.get('filename', '')}",
                     f"📊 Total rows: {analysis.get('total_rows', 0)}",
                     "",
                     "🔍 Detected columns:"]
            mapping = analysis.get("mapping", {})
            for key, val in mapping.items():
                if val:
                    conf = analysis.get("confidence", {}).get(key, (val, "medium"))
                    conf_str = conf[1] if isinstance(conf, tuple) else "medium"
                    lines.append(f" • {key.capitalize()}: '{val}' (confidence: {conf_str})")
            lines.append("")
            lines.append(f"✅ Valid emails found: {analysis.get('valid_emails', 0)}")
            lines.append(f"❌ Invalid emails: {analysis.get('invalid_emails', 0)}")
            if analysis.get("ready_to_import"):
                lines.append("\n✅ Ready to import! Say 'smart import <file> to school'")
            else:
                lines.append("\n⚠️ Not ready — email column not detected confidently.")
            return "\n".join(lines)

        elif action == "preview_import":
            preview = result.get("import_preview", {})
            if not preview:
                return "Could not generate preview."
            lines = [f"📁 {preview.get('filename', '')} — {preview.get('total_rows', 0)} rows",
                     "",
                     "🔍 Detected mapping:"]
            for key, val in preview.get("detected_mapping", {}).items():
                if val:
                    lines.append(f" {key}: {val}")
            lines.append("")
            lines.append("📋 First few rows preview:")
            for i, row in enumerate(preview.get("preview", []), 1):
                lines.append(f" Row {i}: {row.get('name', '')} <{row.get('email', '')}> @ {row.get('org', '')}")
                if row.get("extra_fields"):
                    extras = ", ".join([f"{k}={v}" for k, v in list(row["extra_fields"].items())[:3]])
                    lines.append(f" Extra: {extras}")
            return "\n".join(lines)

        elif action == "help":
            return """Here's what I can do, sir:

SMART IMPORT:
 "analyze file leads.xlsx" -- See what columns I detected
 "preview import leads.xlsx" -- Preview first 5 rows
 "smart import leads.xlsx to school" -- Auto-import + create batches

SEQUENCES:
 "start engine" -- Begin auto-sending
 "status" -- Full campaign overview
 "send school day 1" -- Manual batch send
 "catch up" -- Send overdue emails

TEMPLATES:
 "sync templates" -- Load from Gmail drafts

MONITORING:
 "check bounces" -- Scan and blacklist
 "check replies" -- Find new responses
 "brief now" -- Send morning brief

BLACKLIST:
 "blacklist email@domain.com"

CONTROL:
 "pause" / "resume" / "stop all"

What would you like to do?"""

        elif action == "memory_query":
            recent = result.get("history", [])
            if not recent:
                return "I don't have much history yet, sir. Let's build some memories together."
            lines = ["Here's what I remember recently:"]
            for i in recent[-5:]:
                lines.append(f" • You: {i['user_input'][:50]}...")
                lines.append(f" Me: {i['raj_response'][:50]}...")
            return "\n".join(lines)

        elif action == "create_campaign":
            r = result.get("create_campaign", {})
            if r.get("success"):
                lines = [f"Campaign '{r.get('name')}' created!", ""]
                lines.append(f"Day 1 batch: {r.get('day1_size', 0)} leads")
                lines.append(f"Auto-advance: {'ON' if r.get('auto_advance') else 'OFF'}")
                if r.get("follow_up_batches"):
                    lines.append(f"Pre-created {len(r.get('follow_up_batches'))} follow-up batches:")
                    for b in r["follow_up_batches"]:
                        lines.append(f" -> {b['name']} (Day {b['day']}) at {b['scheduled']}")
                lines.append("")
                lines.append("Click Start on Day 1 batch to begin. Days 3,5,7,10 will auto-launch.")
                return "\n".join(lines)
            else:
                return f"Campaign creation failed: {r.get('error', 'Unknown error')}"

        elif action == "list_campaigns":
            campaigns = result.get("campaigns", [])
            if not campaigns:
                return "No campaigns yet, sir. Say 'create campaign school 50' to start one."
            lines = ["Campaigns:", ""]
            for c in campaigns:
                status_emoji = {"draft": "📝", "active": "🟢", "paused": "⏸️", "completed": "✅"}.get(c.get("status"), "❓")
                lines.append(f"{status_emoji} ID {c['id']}: {c['name']} ({c['sequence_id'].upper()})")
                lines.append(f" Status: {c.get('status', 'unknown').upper()} | Leads: {c.get('total_leads', 0)} | Auto-advance: {'ON' if c.get('auto_advance') else 'OFF'}")
                lines.append("")
            lines.append("Say 'start campaign <id>' to launch, or 'pause campaign <id>' to stop.")
            return "\n".join(lines)

        elif action == "start_campaign":
            if result.get("started"):
                return f"Campaign {result['campaign_id']} started! Batch '{result['batch_name']}' is now running. Day 3 will auto-schedule when Day 1 completes."
            else:
                return f"Could not start: {result.get('error', 'Unknown error')}"

        elif action == "pause_campaign":
            if result.get("paused"):
                return f"Campaign {result['campaign_id']} paused. All running batches stopped. Say 'start campaign {result['campaign_id']}' to resume."
            else:
                return "Pause failed, sir."

        elif action == "archive_campaign":
            if result.get("archived"):
                return f"Campaign {result['campaign_id']} archived. All sequence data preserved."
            else:
                return "Archive failed, sir."

        elif action == "chat":
            return result.get("response", "I'm here, sir. What would you like me to do?")

        return "Done, sir."
