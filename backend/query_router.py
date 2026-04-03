from semantic_router import Route
from semantic_router import SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder
from backend.config import settings

class QueryRouter:
    def __init__(self):
        # ---------------------------------------------------------
        # Define the 5 semantic routes with 10 utterances each
        # ---------------------------------------------------------

        self.finance_route = Route(
            name="finance",
            utterances=[
                "what is the company revenue for Q3?",
                "show me the budget allocations for next year",
                "summarize the latest financial metrics",
                "who are our top investors?",
                "what is our current burn rate?",
                "find the annual report for FY2024",
                "what were our profit margins last quarter?",
                "how much did we spend on operational costs?",
                "give me a breakdown of operational spend",
                "what are the financial projections for Q4?",
                "calculate the B2B bulk payments total",
                "show the revenue growth forecast for 2025"
            ],
        )

        self.engineering_route = Route(
            name="engineering",
            utterances=[
                "where can I find the system architecture document?",
                "how do I onboard to the platform?",
                "what is the API reference for the new microservice?",
                "show me the latest incident runbooks",
                "how do I trigger a deployment?",
                "what are the system SLAs for 2024?",
                "find the engineering master doc",
                "show me the sprint velocity metrics",
                "how does the authentication flow work?",
                "PostgreSQL database transactional data ACID compliance",
                "microservices-based cloud-native system architecture",
                "Uptime target for Payment Service in 2024",
                "target P95 latency for Auth Service",
                "Prometheus Grafana ELK Stack monitoring",
                "average story points per sprint in Q4",
                "How many deployments were executed in total during 2024?",
                "technical debt budget allocation percentage",
                "rollback rate for production deployments in 2024"
            ],
        )

        self.marketing_route = Route(
            name="marketing",
            utterances=[
                "what were the results of our last marketing campaign?",
                "where are the brand guidelines located?",
                "show me the competitor analysis report",
                "what is our market share in the B2B sector?",
                "how many customers did we acquire last month?",
                "find the marketing report for Q2 2024",
                "what is our go-to-market strategy?",
                "how did our social media campaign perform?",
                "Expansion to Southeast Asia Thailand Vietnam Indonesia",
                "Key feature release InstantPay Q1 2024",
                "Loyalty Platform launch in Q3 2024",
                "Wealth management AI recommendations",
                "average feature time-to-production in 2024",
                "Phase 1 of Cryptocurrency wallet integration"
            ],
        )

        self.hr_general_route = Route(
            name="general",
            utterances=[
                "what is the company leave policy?",
                "how many vacation days do I get?",
                "how many sick leaves do i get in an year?",
                "tell me about the sick leave policy",
                "where is the HR handbook?",
                "what are the employee benefits?",
                "what is the code of conduct?",
                "How do I expense a work dinner?",
                "When was FinSolve Technologies founded and where is its headquarters?",
                "When was the company founded?",
                "Where is the company based?",
                "Bangalore India headquarters",
                "How many employees does FinSolve Technologies currently have?",
                "mission statement of FinSolve Technologies",
                "Which regions does FinSolve operate in?",
                "senior management organizational hierarchy CTO",
                "FinSolve cost-to-company CTC model",
                "What is the remote work policy?"
            ],
        )

        self.cross_department_route = Route(
            name="cross_department",
            utterances=[
                "summarize everything we did as a company last year",
                "what are all the major updates across all departments?",
                "give me a complete overview of the business",
                "search all documents for the term 'Project Apollo'",
                "strategic alignment goals for the whole company",
                "show me the company-wide OKRs",
                "details of latest product launch across marketing and engineering",
                "big picture strategy report",
                "comprehensive summary of our corporate strategy",
                "Annual performance review of all departments"
            ],
        )

        # Initialize encoder from settings
        self.encoder = HuggingFaceEncoder(name=settings.semantic_router_encoder)

        self.routes = [
            self.finance_route,
            self.engineering_route,
            self.marketing_route,
            self.hr_general_route,
            self.cross_department_route
        ]

        # Create the router
        self.router = SemanticRouter(encoder=self.encoder, routes=self.routes, auto_sync="local")

    def get_semantic_route(self, query: str) -> str:
        """
        Classifies a user query into one of the 5 defined routes.
        Returns the name of the route, or 'cross_department' fallback.
        """
        route_choice = self.router(query)
        
        if route_choice and route_choice.name:
            return route_choice.name
            
        return "cross_department"  # Fallback intentionally to standard Qdrant broad search

    def check_route_access(self, route_name: str, user_role: str) -> dict:
        """
        Validates if the user's role is allowed to query the selected route.
        Returns: {"allowed": bool, "message": str}
        """
        # 1. Broadly accessible routes
        if route_name in ["general", "cross_department"]:
            return {"allowed": True, "message": "General query allowing standard RBAC retrieval"}
            
        # 2. Universal access roles
        if user_role in ["c_level", "admin"]:
            return {"allowed": True, "message": f"Full access granted for {user_role}"}
            
        # 3. Specific department access restriction
        if route_name == user_role:
            return {"allowed": True, "message": f"Access granted to {route_name} documents."}
            
        # 4. Access Denied logic
        return {
            "allowed": False, 
            "message": f"You don't have access to {route_name} documents."
        }

if __name__ == "__main__":
    router = QueryRouter()
    print(router.get_semantic_route("what is our go-to-market strategy?"))