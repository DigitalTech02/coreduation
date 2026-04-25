"""Pydantic models for the semantic video generation engine.

Defines the structured action vocabulary that the LLM outputs instead of raw
Manim code.  Each action type maps to a deterministic renderer function.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SceneType(str, Enum):
    concept = "concept"
    code = "code"
    visualization = "visualization"


# LLMs often return pedagogical labels; we only persist concept | code | visualization.
_SCENE_TYPE_ALIASES: dict[str, SceneType] = {
    "introduction": SceneType.concept,
    "overview": SceneType.concept,
    "hook": SceneType.concept,
    "core_concept": SceneType.concept,
    "concept": SceneType.concept,
    "summary": SceneType.concept,
    "analysis_comparison": SceneType.concept,
    "analysis": SceneType.concept,
    "comparison": SceneType.concept,
    "visual_walkthrough": SceneType.visualization,
    "protocol_detail": SceneType.visualization,
    "visualization": SceneType.visualization,
    "visual": SceneType.visualization,
    "diagram": SceneType.visualization,
    "implementation": SceneType.code,
    "config": SceneType.code,
    "code": SceneType.code,
}


def coerce_scene_type(value) -> SceneType:
    """Map free-form or alias strings from the LLM to SceneType."""
    if isinstance(value, SceneType):
        return value
    if not isinstance(value, str):
        return SceneType.concept
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    if key in _SCENE_TYPE_ALIASES:
        return _SCENE_TYPE_ALIASES[key]
    try:
        return SceneType(key)
    except ValueError:
        return SceneType.concept


class NodeIconType(str, Enum):
    computer = "computer"
    server = "server"
    router = "router"
    switch = "switch"
    firewall = "firewall"
    cloud = "cloud"
    phone = "phone"
    database = "database"
    load_balancer = "load_balancer"
    generic = "generic"


_ICON_TYPE_ALIASES: dict[str, NodeIconType] = {
    "person": NodeIconType.generic,
    "user": NodeIconType.generic,
    "client": NodeIconType.computer,
    "laptop": NodeIconType.computer,
    "desktop": NodeIconType.computer,
    "pc": NodeIconType.computer,
    "host": NodeIconType.computer,
    "node": NodeIconType.generic,
    "gateway": NodeIconType.router,
    "hub": NodeIconType.switch,
    "storage": NodeIconType.database,
    "db": NodeIconType.database,
    "cdn": NodeIconType.cloud,
    "vm": NodeIconType.server,
    "container": NodeIconType.server,
    "lb": NodeIconType.load_balancer,
}


def coerce_icon_type(value) -> NodeIconType:
    if isinstance(value, NodeIconType):
        return value
    if not isinstance(value, str):
        return NodeIconType.generic
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return NodeIconType(key)
    except ValueError:
        pass
    if key in _ICON_TYPE_ALIASES:
        return _ICON_TYPE_ALIASES[key]
    return NodeIconType.generic


class ConnectionStyle(str, Enum):
    solid = "solid"
    dashed = "dashed"
    dotted = "dotted"


class TopologyLayout(str, Enum):
    star = "star"
    mesh = "mesh"
    ring = "ring"
    bus = "bus"
    tree = "tree"
    custom = "custom"


class StackType(str, Enum):
    osi = "osi"
    tcp_ip = "tcp_ip"


class CloudServiceType(str, Enum):
    compute = "compute"
    storage = "storage"
    database = "database"
    serverless = "serverless"
    api_gateway = "api_gateway"
    cdn = "cdn"
    load_balancer = "load_balancer"
    queue = "queue"
    cache = "cache"
    dns = "dns"
    generic = "generic"


# ---------------------------------------------------------------------------
# Action models — Category 1: Network Topology
# ---------------------------------------------------------------------------

class CreateNode(BaseModel):
    type: Literal["create_node"] = "create_node"
    id: str
    label: str
    sublabel: str = ""
    position: str = Field(
        default="center",
        description="Placement hint: left, right, center, top, bottom, or 'x,y' coords",
    )
    icon_type: NodeIconType = NodeIconType.generic

    @field_validator("icon_type", mode="before")
    @classmethod
    def _normalize_icon(cls, v):
        return coerce_icon_type(v)


class CreateConnection(BaseModel):
    type: Literal["create_connection"] = "create_connection"
    id: str = ""
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    style: ConnectionStyle = ConnectionStyle.solid
    label: str = ""
    color: str = ""
    bidirectional: bool = False

    model_config = {"populate_by_name": True}


class UpdateNode(BaseModel):
    type: Literal["update_node"] = "update_node"
    id: str
    label: str | None = None
    sublabel: str | None = None
    highlight_color: str | None = None


class RemoveElement(BaseModel):
    type: Literal["remove_element"] = "remove_element"
    id: str


class TopologyNodeDef(BaseModel):
    id: str
    label: str
    sublabel: str = ""
    icon_type: NodeIconType = NodeIconType.generic

    @field_validator("icon_type", mode="before")
    @classmethod
    def _normalize_icon(cls, v):
        return coerce_icon_type(v)


class CreateTopology(BaseModel):
    type: Literal["create_topology"] = "create_topology"
    layout: TopologyLayout
    nodes: list[TopologyNodeDef]
    center_node_id: str | None = None


# ---------------------------------------------------------------------------
# Category 2: Packet & Message Flow
# ---------------------------------------------------------------------------

class SendPacket(BaseModel):
    type: Literal["send_packet"] = "send_packet"
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    label: str = ""
    color: str = "blue"
    speed: float = Field(default=1.0, description="Multiplier: <1 slower, >1 faster")

    model_config = {"populate_by_name": True}


class SendBroadcast(BaseModel):
    type: Literal["send_broadcast"] = "send_broadcast"
    from_node: str = Field(alias="from")
    label: str = ""
    color: str = "yellow"

    model_config = {"populate_by_name": True}


class SequenceMessage(BaseModel):
    from_participant: str = Field(alias="from")
    to_participant: str = Field(alias="to")
    label: str
    color: str = ""
    dashed: bool = False

    model_config = {"populate_by_name": True}


class ShowSequenceDiagram(BaseModel):
    type: Literal["show_sequence_diagram"] = "show_sequence_diagram"
    participants: list[str]
    messages: list[SequenceMessage]
    title: str = ""


# ---------------------------------------------------------------------------
# Category 3: Data Structures & Breakdowns
# ---------------------------------------------------------------------------

class ShowLayerStack(BaseModel):
    type: Literal["show_layer_stack"] = "show_layer_stack"
    stack_type: StackType = StackType.osi
    highlight_layers: list[int] = Field(default_factory=list)
    title: str = ""


class HeaderField(BaseModel):
    name: str
    size: str = ""
    highlight: bool = False

    @field_validator("size", mode="before")
    @classmethod
    def _coerce_size(cls, v):
        if v is None:
            return ""
        return str(v)


class ShowHeaderBreakdown(BaseModel):
    type: Literal["show_header_breakdown"] = "show_header_breakdown"
    title: str = ""
    fields: list[HeaderField]
    highlight_field: str | None = None


class TableRow(BaseModel):
    cells: list[str]
    highlight: bool = False


class ShowTable(BaseModel):
    type: Literal["show_table"] = "show_table"
    title: str = ""
    headers: list[str]
    rows: list[TableRow]
    highlight_row: int | None = None


class ShowMath(BaseModel):
    type: Literal["show_math"] = "show_math"
    expression: str
    label: str = ""


# ---------------------------------------------------------------------------
# Category 4: Presentation & Comparison
# ---------------------------------------------------------------------------

class ShowTextBlock(BaseModel):
    type: Literal["show_text_block"] = "show_text_block"
    title: str = ""
    body: str = ""
    position: str = "center"


class ShowCodeBlock(BaseModel):
    type: Literal["show_code_block"] = "show_code_block"
    title: str = ""
    language: str = ""
    lines: list[str]
    highlight_lines: list[int] = Field(default_factory=list)


class ComparisonColumn(BaseModel):
    title: str
    items: list[str]


class ShowComparison(BaseModel):
    type: Literal["show_comparison"] = "show_comparison"
    left: ComparisonColumn
    right: ComparisonColumn
    title: str = ""


class ShowBulletList(BaseModel):
    type: Literal["show_bullet_list"] = "show_bullet_list"
    title: str = ""
    items: list[str]
    progressive: bool = True


# ---------------------------------------------------------------------------
# Category 5: Cloud Architecture
# ---------------------------------------------------------------------------

class CreateCloudRegion(BaseModel):
    type: Literal["create_cloud_region"] = "create_cloud_region"
    id: str
    label: str
    parent_id: str | None = None
    position: str = "center"


class CreateCloudService(BaseModel):
    type: Literal["create_cloud_service"] = "create_cloud_service"
    id: str
    label: str
    service_type: CloudServiceType = CloudServiceType.generic
    region_id: str | None = None
    position: str = "center"


class DataFlowHop(BaseModel):
    node_id: str
    label: str = ""


class ShowDataFlow(BaseModel):
    type: Literal["show_data_flow"] = "show_data_flow"
    hops: list[DataFlowHop]
    label: str = ""
    color: str = "cyan"


# ---------------------------------------------------------------------------
# Category 6: Retention & Camera
# ---------------------------------------------------------------------------

class PulseElement(BaseModel):
    type: Literal["pulse_element"] = "pulse_element"
    target_id: str
    intensity: float = 1.15
    duration: float = 0.5
    color: str | None = None


class FocusCamera(BaseModel):
    type: Literal["focus_camera"] = "focus_camera"
    target_id: str | None = None
    zoom: float = 1.2
    duration: float = 1.0
    x: float | None = None
    y: float | None = None


class ResetCamera(BaseModel):
    type: Literal["reset_camera"] = "reset_camera"
    duration: float = 1.0


class ShowProgress(BaseModel):
    type: Literal["show_progress"] = "show_progress"
    label: str
    current_step: int
    total_steps: int
    style: str = "sleek"


class UpdateProgress(BaseModel):
    type: Literal["update_progress"] = "update_progress"
    label: str
    current_step: int
    total_steps: int


class EmphasizeText(BaseModel):
    type: Literal["emphasize_text"] = "emphasize_text"
    text: str
    emphasis_type: str = "pop"
    duration: float = 1.0


class ShakeElement(BaseModel):
    type: Literal["shake_element"] = "shake_element"
    target_id: str
    duration: float = 0.5
    intensity: float = 0.15


class DimExcept(BaseModel):
    type: Literal["dim_except"] = "dim_except"
    target_ids: list[str]
    opacity: float = 0.25
    duration: float = 0.5


class RestoreOpacity(BaseModel):
    type: Literal["restore_opacity"] = "restore_opacity"
    duration: float = 0.5


class AddCallout(BaseModel):
    type: Literal["add_callout"] = "add_callout"
    target_id: str
    text: str
    position: str = "auto"
    duration: float = 2.0


class SceneTransition(BaseModel):
    type: Literal["scene_transition"] = "scene_transition"
    transition_type: str = "wipe"
    label: str | None = None
    duration: float = 0.8


# ---------------------------------------------------------------------------
# Union of all action types
# ---------------------------------------------------------------------------

_VisualActionUnion = Union[
    CreateNode,
    CreateConnection,
    UpdateNode,
    RemoveElement,
    CreateTopology,
    SendPacket,
    SendBroadcast,
    ShowSequenceDiagram,
    ShowLayerStack,
    ShowHeaderBreakdown,
    ShowTable,
    ShowMath,
    ShowTextBlock,
    ShowCodeBlock,
    ShowComparison,
    ShowBulletList,
    CreateCloudRegion,
    CreateCloudService,
    ShowDataFlow,
    PulseElement,
    FocusCamera,
    ResetCamera,
    ShowProgress,
    UpdateProgress,
    EmphasizeText,
    ShakeElement,
    DimExcept,
    RestoreOpacity,
    AddCallout,
    SceneTransition,
]

VisualAction = Annotated[_VisualActionUnion, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# Scene & Script models (what the LLM returns)
# ---------------------------------------------------------------------------

class SemanticScene(BaseModel):
    """A single scene in the semantic video script."""

    scene_id: str
    title: str
    type: SceneType
    narration: str
    visual_description: str
    actions: list[VisualAction]
    estimated_duration: float

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_scene_type(cls, v):
        return coerce_scene_type(v)


class RetentionBeat(BaseModel):
    """Marker for a re-hook moment in the narration."""

    scene_id: str = ""
    text: str = ""


class SemanticVideoScript(BaseModel):
    """Complete video script as returned by the LLM."""

    topic: str
    scenes: list[SemanticScene]

    video_title: str = ""
    video_hook: str = ""
    open_loop_question: str = ""
    open_loop_resolution_scene_id: str = ""
    retention_beats: list[RetentionBeat | str] = Field(default_factory=list)
    target_audience: str = ""
    emotional_tone: str = ""
    suggested_thumbnail_text: str = ""
    suggested_youtube_title: str = ""


# ---------------------------------------------------------------------------
# Internal enriched scene (after TTS)
# ---------------------------------------------------------------------------

class EnrichedScene(BaseModel):
    """Scene enriched with audio/video paths after TTS and rendering."""

    scene_id: str
    title: str
    type: SceneType
    narration: str
    visual_description: str
    actions: list[VisualAction]
    estimated_duration: float
    audio_path: str | None = None
    audio_duration: float | None = None
    video_path: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_scene_type_enriched(cls, v):
        return coerce_scene_type(v)


class EnrichedVideoScript(BaseModel):
    """Full video script with runtime enrichment."""

    topic: str
    scenes: list[EnrichedScene]
    category: str = ""
    title_card_subtitle: str = ""

    video_title: str = ""
    video_hook: str = ""
    open_loop_question: str = ""
    open_loop_resolution_scene_id: str = ""
    retention_beats: list[RetentionBeat | str] = Field(default_factory=list)
    target_audience: str = ""
    emotional_tone: str = ""
    suggested_thumbnail_text: str = ""
    suggested_youtube_title: str = ""

    @classmethod
    def from_llm_output(cls, llm_script: SemanticVideoScript) -> EnrichedVideoScript:
        return cls(
            topic=llm_script.topic,
            scenes=[EnrichedScene(**s.model_dump()) for s in llm_script.scenes],
            video_title=llm_script.video_title,
            video_hook=llm_script.video_hook,
            open_loop_question=llm_script.open_loop_question,
            open_loop_resolution_scene_id=llm_script.open_loop_resolution_scene_id,
            retention_beats=llm_script.retention_beats,
            target_audience=llm_script.target_audience,
            emotional_tone=llm_script.emotional_tone,
            suggested_thumbnail_text=llm_script.suggested_thumbnail_text,
            suggested_youtube_title=llm_script.suggested_youtube_title,
        )
