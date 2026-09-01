class UraConfig:
    skill_event_weight: list[int]
    reset_skill_event_weight_list: list[str]

    def __init__(self, config: dict):
        if "skillEventWeight" not in config or "resetSkillEventWeightList" not in config:
            raise ValueError("错误的配置: 必须配置 'skillEventWeight' 和 'resetSkillEventWeightList'")
        self.skill_event_weight = config["skillEventWeight"]
        self.reset_skill_event_weight_list = config["resetSkillEventWeightList"]
    
    def removeSkillFromList(self, skill: str):
        if skill in self.reset_skill_event_weight_list:
            self.reset_skill_event_weight_list.remove(skill)
            # 如果技能列表空了, 重置权重
            # 如果一开始列表就是空的, 这个分支就不会触发, 也不会重置权重
            if len(self.reset_skill_event_weight_list) == 0:
                self.skill_event_weight = [0, 0, 0]
    
    def getSkillEventWeight(self, date: int) -> int:
        if date <= 24:
            return self.skill_event_weight[0]
        elif date <= 48:
            return self.skill_event_weight[1]
        else:
            return self.skill_event_weight[2]

class AoharuConfig:

    preliminary_round_selections: list[int]
    aoharu_team_name_selection: int

    def __init__(self, config: dict):
        if "preliminaryRoundSelections" not in config or "aoharuTeamNameSelection" not in config:
            raise ValueError("错误的配置: 必须配置 'preliminaryRoundSelections' 和 'aoharuTeamNameSelection'")
        self.preliminary_round_selections = config["preliminaryRoundSelections"]
        self.aoharu_team_name_selection = config["aoharuTeamNameSelection"]

    def get_opponent(self, round_index: int) -> int:
        """ 获取指定轮次的对手索引, 索引从0开始, 预赛第一轮为0 """
        if round_index < 0 or round_index >= len(self.preliminary_round_selections):
            raise IndexError("轮次索引超出范围")
        return self.preliminary_round_selections[round_index]
    
class KaisenConfig:
    """凯旋杯(凯旋门 L'Arc)剧本配置.

    A档: 占位结构, 具体配置项(远征策略等)待 B/C 档按实际机制补充。
    所有字段可选, 缺失时使用默认值, 保证旧任务/预设兼容。
    """

    def __init__(self, config: dict = None):
        if config is None:
            config = {}
        # 养成模式: 1=普通模式, 2=挑战训练员技能考试
        self.kaisen_mode = config.get("kaisenMode", 1)
        # TODO(C档): 按凯旋杯机制补充配置项, 例如:
        # - 远征/海外训练相关开关
        # - 凯旋门赏目标赛处理
        # - シナリオリンク相关

class ScenarioConfig:
    """ 所有场景的配置 """
    ura_config: UraConfig = None
    aoharu_config: AoharuConfig = None
    kaisen_config: KaisenConfig = None
    
    def __init__(self, ura_config: UraConfig = None, aoharu_config: AoharuConfig = None,
                 kaisen_config: KaisenConfig = None):
        self.ura_config = ura_config
        self.aoharu_config = aoharu_config
        self.kaisen_config = kaisen_config
