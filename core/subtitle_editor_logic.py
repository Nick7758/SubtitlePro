import os
import shutil
import srt
from datetime import timedelta
from typing import List, Tuple, Optional


def is_chinese(text: str) -> bool:
    """启发式判断是否为中文"""
    # 简单通过中文字符范围判断
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


def swap_chinese_english(subtitles: List[srt.Subtitle], chinese_up: bool) -> List[srt.Subtitle]:
    """
    交换字幕中的中文和英文位置
    
    Args:
        subtitles: 字幕列表
        chinese_up: True表示中文在上，False表示其他语言在上
    
    Returns:
        处理后的字幕列表
    """
    if not subtitles:
        return subtitles
    
    # 检查当前第一条字幕的第一行是否为中文
    first_subtitle_content = subtitles[0].content.lstrip('\n').split('\n')[0]
    current_up_language = is_chinese(first_subtitle_content)
    user_up_language = True if chinese_up == True else False
    
    # 如果当前顺序与期望顺序一致，直接返回
    if current_up_language == user_up_language:
        return subtitles
    
    # 否则交换每条字幕的两行内容
    swapped_all_subtitles = []
    index = 1
    for sub in subtitles:
        tem_subcontent = sub.content.lstrip('\n').rstrip('\n').split('\n')
        
        # 如果只有一行，不进行交换
        if len(tem_subcontent) < 2:
            swapped_all_subtitles.append(sub)
            index += 1
            continue
        
        second_to_up = tem_subcontent[-1]
        first_to_down = tem_subcontent[0]
        temp_sub = srt.Subtitle(
            index=index, 
            start=sub.start, 
            end=sub.end, 
            content=second_to_up + '\n' + first_to_down
        )
        swapped_all_subtitles.append(temp_sub)
        index += 1
    
    return swapped_all_subtitles


def parse_subtitle_file(filepath: str) -> Tuple[List[srt.Subtitle], str]:
    """
    解析字幕文件，支持多种格式
    
    Args:
        filepath: 字幕文件路径
    
    Returns:
        (字幕列表, 原始格式)
    """
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 尝试使用srt库解析（支持srt格式）
        if ext in ['.srt', '.ass', '.ssa', '.vtt']:
            try:
                subtitles = list(srt.parse(content))
                return subtitles, ext[1:]  # 去掉点号返回格式
            except:
                # 如果解析失败，尝试按行解析
                pass
        
        # 如果上述方法失败，返回空列表
        return [], ext[1:]
    
    except Exception as e:
        raise Exception(f"无法解析字幕文件: {str(e)}")


def save_subtitle_file(subtitles: List[srt.Subtitle], filepath: str, format: str) -> None:
    """
    保存字幕文件到指定格式
    
    Args:
        subtitles: 字幕列表
        filepath: 保存路径
        format: 保存格式 (srt, ass, ssa, vtt)
    """
    format = format.lower()
    
    # 生成SRT格式内容
    srt_content = srt.compose(subtitles)
    
    # 根据格式保存
    if format == 'srt':
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(srt_content)
    elif format in ['ass', 'ssa']:
        # ASS/SSA格式需要使用pysubs2库
        try:
            import pysubs2
            subs = pysubs2.SSAFile()
            for sub in subtitles:
                event = pysubs2.SSAEvent(
                    start=int(sub.start.total_seconds() * 1000),
                    end=int(sub.end.total_seconds() * 1000),
                    text=sub.content.replace('\n', '\\N')
                )
                subs.append(event)
            subs.save(filepath)
        except ImportError:
            # 如果没有pysubs2，降级为SRT格式
            with open(filepath.replace(f'.{format}', '.srt'), 'w', encoding='utf-8') as f:
                f.write(srt_content)
            raise Exception(f"需要安装pysubs2库才能保存{format.upper()}格式，已保存为SRT格式")
    elif format == 'vtt':
        # VTT格式转换
        vtt_content = "WEBVTT\n\n"
        for sub in subtitles:
            start = format_vtt_time(sub.start)
            end = format_vtt_time(sub.end)
            vtt_content += f"{start} --> {end}\n{sub.content}\n\n"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(vtt_content)
    else:
        # 默认保存为SRT
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(srt_content)


def format_vtt_time(td: timedelta) -> str:
    """将timedelta转换为VTT时间格式"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def create_backup(filepath: str) -> str:
    """
    创建文件备份
    
    Args:
        filepath: 原文件路径
    
    Returns:
        备份文件路径
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    backup_path = filepath + '.bak'
    
    # 如果备份文件已存在，先删除
    if os.path.exists(backup_path):
        os.remove(backup_path)
    
    # 复制文件
    shutil.copy2(filepath, backup_path)
    
    return backup_path


def parse_srt_time(time_str: str) -> timedelta:
    """
    解析SRT时间格式字符串
    
    Args:
        time_str: 时间字符串，如 "00:00:01,500"
    
    Returns:
        timedelta对象
    """
    try:
        # SRT格式: HH:MM:SS,mmm
        time_str = time_str.strip()
        time_parts = time_str.replace(',', '.').split(':')
        hours = int(time_parts[0])
        minutes = int(time_parts[1])
        seconds_parts = time_parts[2].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        
        return timedelta(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)
    except Exception as e:
        raise ValueError(f"无效的时间格式: {time_str}, 错误: {str(e)}")


def format_srt_time(td: timedelta) -> str:
    """
    将timedelta转换为SRT时间格式
    
    Args:
        td: timedelta对象
    
    Returns:
        SRT格式时间字符串
    """
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = td.microseconds // 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
