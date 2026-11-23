"""
文本生成功能实现 - 修复字符类型选择问题，支持按比例均匀分配字符
"""

import random
import string
import threading


class TextGenerator:
    """文本生成器 - 修复字符类型选择问题，支持按比例均匀分配字符"""

    def __init__(self):
        self.stop_generation_flag = False

    def _get_character_pools(self, char_types):
        """根据字符类型设置获取字符池字典 - 返回每种类型的独立字符池"""
        char_pools = {}

        # 英文字符
        if char_types.get('include_english', True):
            char_pools['english'] = string.ascii_letters

        # 数字字符
        if char_types.get('include_digits', True):
            char_pools['digits'] = string.digits

        # 中文字符 - 常用汉字范围
        if char_types.get('include_chinese', True):
            # 常用汉字范围
            common_chinese_chars = [
                '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严'
            ]
            char_pools['chinese'] = ''.join(common_chinese_chars)

        # 特殊字符
        if char_types.get('include_special', True):
            special_chars = '~!@#$%^&*()_+-=[]{}|;:,.<>?/ '
            char_pools['special'] = special_chars

        # Unicode字符
        if char_types.get('include_unicode', True):
            unicode_chars = [
                '★', '☆', '♡', '♥', '♦', '♣', '♠', '●', '○', '◎', '◇', '◆', '□', '■', '△', '▲', '▽', '▼',
                '→', '←', '↑', '↓', '↔', '↕', '✔', '✓', '✕', '✖', '✨', '⭐', '🌟', '☀', '☁', '☂', '☃',
                '☎', '☑', '☒', '☔', '☕', '☘', '☝', '☠', '☢', '☣', '☦', '☪', '☮', '☯', '☸', '☹', '☺',
                '♀', '♂', '♩', '♪', '♫', '♬', '♾', '⚓', '⚡', '⚪', '⚫', '⚽', '⚾', '⛄', '⛅', '⛎', '⛔',
                '⛪', '⛲', '⛳', '⛵', '⛺', '⛽', '✂', '✈', '✉', '✌', '✍', '✏', '✒', '✔', '✖', '✝', '✡',
                '✨', '✳', '✴', '❄', '❇', '❌', '❎', '❓', '❔', '❕', '❗', '❤', '➡', '⭐', '🌟', '🙂', '😀',
                '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇', '🙃', '😉', '😌', '😍', '🥰', '😘', '😗',
                '😙', '😚', '😋', '😛', '😝', '😜', '🤪', '🤨', '🧐', '🤓', '😎', '🤩', '🥳', '😏', '😒', '😞',
                '😔', '😟', '😕', '🙁', '☹', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠', '😡', '🤬',
                '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '🤥', '😶', '😐',
                '😑', '😬', '🙄', '😯', '😦', '😧', '😮', '😲', '🥱', '😴', '🤤', '😪', '😵', '🤐', '🥴', '🤢'
            ]
            char_pools['unicode'] = ''.join(unicode_chars)

        return char_pools

    def generate_text(self, length, include_english=True, include_chinese=True,
                     include_digits=True, include_special=True, include_unicode=True,
                     progress_callback=None, status_callback=None):
        """生成文本 - 修复字符类型选择问题，按比例均匀分配字符"""
        self.stop_generation_flag = False

        # 构建字符类型字典
        char_types = {
            'include_english': include_english,
            'include_chinese': include_chinese,
            'include_digits': include_digits,
            'include_special': include_special,
            'include_unicode': include_unicode
        }

        # 获取字符池字典
        char_pools = self._get_character_pools(char_types)

        if not char_pools:
            raise ValueError("没有选择任何字符类型，请至少选择一种字符类型")

        # 计算每种字符类型应该生成多少个字符
        pool_count = len(char_pools)
        base_chars_per_pool = length // pool_count
        remainder = length % pool_count

        if status_callback:
            status_callback("开始生成文本...")

        # 生成字符列表
        all_chars = []

        for i, (pool_name, char_pool) in enumerate(char_pools.items()):
            # 计算该字符池应该生成的字符数量
            chars_needed = base_chars_per_pool
            if i < remainder:  # 将余数分配到前几个字符池
                chars_needed += 1

            # 从该字符池中随机选择指定数量的字符
            if len(char_pool) >= chars_needed:
                selected_chars = random.sample(char_pool, chars_needed)
            else:
                # 如果字符池中的字符不够，重复选择
                selected_chars = [random.choice(char_pool) for _ in range(chars_needed)]

            all_chars.extend(selected_chars)

            # 更新进度
            if progress_callback:
                progress = min(100, (len(all_chars) / length * 100))
                progress_callback(progress)

            if status_callback and len(all_chars) % 5000 == 0:
                status_callback(f"已生成 {len(all_chars)}/{length} 字符")

            if self.stop_generation_flag:
                break

        # 打乱字符顺序
        if not self.stop_generation_flag:
            random.shuffle(all_chars)

        # 组合成最终文本
        result_text = ''.join(all_chars)

        if status_callback and not self.stop_generation_flag:
            status_callback("文本生成完成")

        return result_text

    def stop_generation(self):
        """停止生成文本"""
        self.stop_generation_flag = True