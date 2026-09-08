# Agentcy presenter script

Estimated length: 7 to 10 minutes

Use this as a guide, rather than reading every line word for word. The slides carry the visual detail. Your job is to explain why each part matters.

## Slide 1: Agentcy

Good morning everyone. Today I am introducing Agentcy, an AI campaign-production workspace designed for Malaysian SMEs.

The idea behind this project is simple. Marketing teams want to move faster, but they cannot hand product claims, brand voice, and publishing decisions to a black box. Agentcy brings campaign planning, image creation, video creation, and human approval into one visible workflow.

By the end of this presentation, I want to show that the main value of Agentcy is not only generation speed. It is the ability to keep a person in control while the system does useful work.

## Slide 2: The campaign-production gap

Most generative tools can produce an initial idea quickly. The more difficult problem starts after that first draft.

For a real brand, the content has to remain accurate. It has to respect the product facts and restrictions. It also has to fit the campaign context, especially when local trends or seasonal events are involved.

Agentcy focuses on that gap. It treats brand truth, local context, and final human control as part of the production process rather than as checks added at the end.

## Slide 3: A campaign workspace, not a prompt box

This is how Agentcy turns the idea into a working product.

The workflow begins with a campaign brief. The planner develops grounded concepts from that brief. Once a concept is approved, a generation crew prepares the copy and visual direction. The system then supports image or video production, with a human approval point before the work moves on.

On the right, you can see the Image Studio. It exposes the agents, the work path, and the points where a human review happens. The user can see what the system is doing instead of waiting for an unexplained output.

## Slide 4: Grounded planning

The planning stage uses a clear hierarchy of information.

First, the campaign brief tells the system what the team wants to achieve. Second, company knowledge provides the product facts, brand voice, approved claims, and restrictions. This is the source of truth.

Trend signals come last. They can suggest a useful creative angle, but they can never become evidence for a product claim. That distinction is important because it prevents the system from treating a popular search topic as a fact about the brand.

Before anything is generated, the reviewer can see the rationale behind the concept and understand where it came from.

## Slide 5: Human approval holds the line

This slide shows the campaign state path. A campaign starts as a draft, moves into planning, waits for plan approval, then enters generation. After generation, it waits again for asset review before it becomes ready to publish.

The key rule is that the campaign cannot skip these stages. The system does not approve its own concept, and it does not publish its own output.

The interface reinforces that rule visually. When a gate opens, the machine recedes and the review work becomes the focus. The work stays there until a person makes a decision.

## Slide 6: Image Studio

Once a team approves a concept, the Image Studio turns it into reviewable creative.

The generation crew writes the copy, plans the image composition, and checks the pairing against the brand knowledge. The renderer keeps the final text under local control, so the system does not depend on an image model to draw accurate captions or product details.

The creative director can request revisions to either the copy or the visuals. However, the revision loop has a fixed limit of two passes. This prevents the workflow from getting stuck and makes sure a reviewer sees work that is clearly marked as passed or flagged.

## Slide 7: Video and cinematic storytelling

Agentcy also extends the same control model to video.

The Video Studio saves the brand, product, target audience, call to action, and storyboard with each project. It renders the final vertical video locally so the captions and product interface stay accurate.

The project also includes a Cinematic Trailer workflow for longer-form storytelling. If optional generated b-roll is unavailable, the video pipeline can fall back to its deterministic render rather than failing completely.

That makes video a repeatable production process instead of a one-off prompt experiment.

## Slide 8: The interface makes control visible

For me, this is an important part of the project. The interface is designed to make the system understandable while it is working.

The agent station shows which agent currently holds the work. The flow graph shows the production path and any revision loops. Amber is reserved for the moment when a human decision is required.

The History screen on the right keeps both the outputs and the record of the work that produced them. A team can reopen a planning pass or crew run later instead of losing the context once a campaign ends.

## Slide 9: A dependable technical foundation

Behind the interface, the project uses a foundation designed for a dependable demonstration and future extension.

FastAPI serves the application and API, while a fixed campaign state machine prevents skipped workflow stages. Chroma stores company knowledge and trend data separately because they have different levels of authority.

LangGraph models the generation crew and its bounded revision process. The system also supports an offline demonstration mode. In this mode, retrieval, gates, and revision logic still run, but the generated copy is clearly labelled as demo content.

This makes it possible to test the complete workflow without needing live model credentials.

## Slide 10: Generative speed with a human owner

To close, Agentcy presents AI marketing as a controlled production system.

It uses brand knowledge to keep campaigns grounded. It can use local signals to inspire ideas without turning them into false claims. It makes the work and the handoff to the human visible throughout the process.

The next useful step would be a focused pilot with one real SME. We would set up the brand profile, run one campaign brief through both approval gates, and compare the approved output with the team’s current production process.

Thank you. I am happy to answer questions or walk through the workflow in the application.

## Likely questions and short answers

**How does Agentcy prevent false product claims?**

The planner treats company knowledge as the source of truth. Trend signals can inspire an angle but cannot justify a claim. Human approval gates provide another check before production and publication.

**Can the system publish automatically?**

No. The campaign state machine requires human approval at the concept and asset-review stages.

**What happens if a model or video provider fails?**

The demo mode works without API keys, and the video workflow has a deterministic fallback so the project can still complete its render path.

**Why use several agents instead of one prompt?**

Different steps need different checks. Separating planning, copy, visual direction, review, and quality checking makes the workflow observable and gives the director a clear place to send revisions.
