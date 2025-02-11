import os, ast
from typing import Optional

from .skillset import SkillSet
from .llm_wrapper import LLMWrapper, LLAMA3, DEEPSEEK
from .vision_skill_wrapper import VisionSkillWrapper
from .utils import print_t
from .minispec_interpreter import MiniSpecValueType, evaluate_value
from .abs.robot_wrapper import RobotType

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

class LLMPlanner():
    def __init__(self, robot_type: RobotType):
        self.llm = LLMWrapper()  # Uses NVIDIA NIM API for LLM requests

        type_folder_name = 'tello' if robot_type == RobotType.TELLO else 'gear'

        # Load predefined prompts
        with open(os.path.join(CURRENT_DIR, f"./assets/{type_folder_name}/prompt_plan.txt"), "r") as f:
            self.prompt_plan = f.read()

        with open(os.path.join(CURRENT_DIR, f"./assets/{type_folder_name}/prompt_probe.txt"), "r") as f:
            self.prompt_probe = f.read()

        with open(os.path.join(CURRENT_DIR, f"./assets/{type_folder_name}/guides.txt"), "r") as f:
            self.guides = f.read()

        with open(os.path.join(CURRENT_DIR, f"./assets/{type_folder_name}/plan_examples.txt"), "r") as f:
            self.plan_examples = f.read()

    def init(self, high_level_skillset: SkillSet, low_level_skillset: SkillSet, vision_skill: VisionSkillWrapper):
        """
        Initialize skillsets and vision capabilities.
        """
        self.high_level_skillset = high_level_skillset
        self.low_level_skillset = low_level_skillset
        self.vision_skill = vision_skill

    def plan(self, task_description: str, scene_description: Optional[str] = None, 
             error_message: Optional[str] = None, execution_history: Optional[str] = None):
        """
        Generates a plan for executing a given task using NVIDIA NIM's LLaMA-3 (low-level) or DeepSeek-R1 (high-level).
        """

        # Classify task complexity and determine which LLM to use
        high_level_tasks = ["plan", "strategy", "complex decision", "multiple steps", "navigation"]
        model_type = "high" if any(word in task_description.lower() for word in high_level_tasks) else "low"

        # Ensure task is correctly formatted
        if not task_description.startswith("["):
            task_description = "[A] " + task_description

        # Get scene description if not provided
        if scene_description is None:
            scene_description = self.vision_skill.get_obj_list()

        # Format the planning prompt
        prompt = f"""
        Task: {task_description}
        Scene: {scene_description}
        Robot Capabilities: 
        - High-level skills: {self.high_level_skillset}
        - Low-level skills: {self.low_level_skillset}
        Guidelines: {self.guides}
        Example Plans: {self.plan_examples}
        Error Log: {error_message}
        Execution History: {execution_history}
        """

        print_t(f"[P] Sending planning request to NVIDIA NIM ({'DeepSeek-R1' if model_type == 'high' else 'LLaMA-3'}) for task: {task_description}")
        
        # Send request to NVIDIA NIM API
        return self.llm.request(prompt, model_type=model_type, stream=False)
    
    def probe(self, question: str) -> MiniSpecValueType:
        """
        Queries the LLM for additional reasoning or clarifications.
        """
        prompt = self.prompt_probe.format(scene_description=self.vision_skill.get_obj_list(), question=question)
        print_t(f"[P] Execution request: {question}")
        return evaluate_value(self.llm.request(prompt, model_type="high")), False