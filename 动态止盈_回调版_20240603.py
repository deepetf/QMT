# encoding:gbk
# Author: 快雪时晴
# Date: 2023-10-16
# Copyright (C) 禄得网 lude.cc All Rights Reserved.
# 修改为多级止盈 - By 张毅-刀把五
# Last modified:	2024/5/25

import logging
from functools import partial
from typing import List, Dict, Optional
from pandas import DataFrame, Series

ACCOUNT: str = '8881522601'# 设置账号
TAKE_PROFIT_ACTIVE_THRESHOLD: float = 6.5 # 激活止盈的最小涨幅(单位%）,当前涨幅大等此值才会触发止盈操作
TAKE_PROFIT_DRAWDOWN: float = 0.3 # 触发止盈最小回撤(单位%），最大回撤大等于此值才会触发止盈操作
TAKE_PROFIT_DEAL_THRESHOLD: float = 1 # 执行止盈的最小涨幅(单位%），当前涨幅大等此值才会触发止盈操作
ONLY_CB: bool = True # 是否只对可转债进行止盈

# 忽略标的列表，不进行止盈
IGNORE_LIST_STR: str = '000001.SZ,600000.SH' 
IGNORE_LIST: List[str] = list(map(lambda code: code.strip().upper(), IGNORE_LIST_STR.split(','))) 

# 日志等级
LOG_LEVEL_STR: str = 'DEBUG'

pos_dicts: Optional[Dict[str, Dict]] = None # 全局持仓

#设置全局持仓的当前止盈水平
profit_level_df = DataFrame()

#定义每个止盈涨幅和卖出量
PROFIT_THRESHOLDS  = {
    'level': [6.3,7.5,8.5],
    'sell_pct': [0.5,0.5,1]		# lelve1 卖一半，level2 卖剩余的一般（1/4），level3 全部卖出
}

PROFIT_THRESHOLDS_DF = DataFrame(PROFIT_THRESHOLDS)

# 生成行情数据df
def gen_data_df(data_dict: Dict) -> DataFrame:
	
	df = DataFrame.from_dict(data_dict, dtype='float').T.reset_index().rename(columns={'index': 'code'})
	# 计算标的均价
	bidPrice_columns = ['bid1','bid2','bid3','bid4','bid5']
	askPrice_columns = ['ask1','ask2','ask3','ask4','ask5']
	df[bidPrice_columns] = df['bidPrice'].apply(Series, index=bidPrice_columns)
	df[askPrice_columns] = df['askPrice'].apply(Series, index=askPrice_columns)
	df['averagePrice'] = (df['bid1'] + df['ask1']) / 2
	df.loc[(df['bid1'] == 0) | (df['ask1'] == 0),'averagePrice'] = df['bid1'] + df['ask1'] # 涨跌停修正

	df.rename(columns={'averagePrice': 'close', 'lastClose': 'pre_close','volume':'vol'}, inplace=True)
	df['amount'] = df['amount'] / 1e4
	df = df[(df.close != 0) & (df.high !=0)] # 现价大于1的标的

	# 计算衍生指标
	df['pct_chg'] = ((df.close / df.pre_close - 1) * 100)
	df['max_pct_chg'] = ((df.high / df.pre_close - 1) * 100)
    
	# 展示列
	display_columns = ['code', 'close', 'pct_chg', 'max_pct_chg', 'high', 'low', 'pre_close', 'vol', 'amount']
	df = df[display_columns]
	return df

# 将持仓对象position映射为dict(更多字段参考:http://docs.thinktrader.net/pages/e148c4/#_5-3-4-position-%E6%8C%81%E4%BB%93%E5%AF%B9%E8%B1%A1)
def position_to_dict(position: object) -> Dict:
	return {
		'code': position.m_strInstrumentID + '.' + position.m_strExchangeID, # 证券代码 000001.SZ
		'name': position.m_strInstrumentName, # 证券名称
		'm_nVolume': position.m_nVolume, # 当前拥股，持仓量
		'm_nCanUseVolume': position.m_nCanUseVolume, # 可用余额，可用持仓，期货不用这个字段，股票的可用数量
		'm_dMarketValue': position.m_dMarketValue, # 市值，合约价值
		'm_dPositionCost': position.m_dPositionCost, # 持仓成本，股票不需要
		'm_dPositionProfit': position.m_dPositionProfit, # 持仓盈亏，股票不需要
		'm_dFloatProfit': position.m_dFloatProfit, # 浮动盈亏，当前量 * （当前价 - 开仓价） * 合约乘数（股票为 1）
	}

# 将委托对象orderInfo映射为dict(更多字段参考:http://docs.thinktrader.net/pages/e148c4/#_5-3-2-order-%E5%A7%94%E6%89%98%E5%AF%B9%E8%B1%A1)
def orderinfo_to_dict(orderinfo: object) -> Dict:
	return {
		'code': orderinfo.m_strInstrumentID + '.' + orderinfo.m_strExchangeID, # 证券代码 000001.SZ
		'name': orderinfo.m_strInstrumentName, # 证券名称
		'm_dLimitPrice': orderinfo.m_dLimitPrice, # 委托价格
		'm_nVolumeTotalOriginal': orderinfo.m_nVolumeTotalOriginal, # 委托数量
		'm_nOffsetFlag': orderinfo.m_nOffsetFlag, # 买卖方向
	}

# 定义全推回调函数
def callback_handle(C: object, data: Dict[str, Dict]) -> None:
	global pos_dicts # 调用全局持仓字典
	global profit_level_df	#全局止盈记录
	
	pos_code = pos_dicts.keys() # 持仓标的list
	if ONLY_CB: # 是否只作用于可转债
		pos_code = set(filter(lambda x: x.startswith(('11', '12')), pos_code))
	data_code = data.keys() # 订阅标的list
	codes = pos_code & data_code #持仓标的和订阅标的的重合标的
	# 若无重合，则退出
	if not codes:
		return
	# 生成行情df
	data_dict = {code: data[code] for code in codes}
	data_df = gen_data_df(data_dict).set_index('code')
	# 生成持仓df
	pos_df = DataFrame.from_dict(pos_dicts, orient='index')
	# 合并持仓数据和行情数据
	df = pos_df[['name', 'm_nCanUseVolume', 'm_nVolume']].merge(data_df[['pct_chg', 'max_pct_chg', 'close']], how='inner', left_index=True, right_index=True)
	
	logging.debug(f'\n行情回调处理结果:\n{df}')
	
	#2024/5/16 改为多级止盈
	
	#获取本次回调的代码
	codes = df.index.tolist()
	#print('\n行情回调codes:\n',codes)
	
	for index, row in df.iterrows():
		
		#获取当前标的当前止盈级别的涨幅
		i = profit_level_df.loc[profit_level_df['code'] == index, 'level'].values[0]
		
		if i < PROFIT_THRESHOLDS_DF.shape[0]:
			CURRENT_ACTIVE_THRESHOLD = PROFIT_THRESHOLDS_DF.iloc[i]['level']
		else:
				logging.debug(f'\n已卖光，卖飞！！！:\n{row}')
				return
				
		#根据止盈级别计算卖出数量
		SELL_PCT = PROFIT_THRESHOLDS_DF.iloc[i]['sell_pct']
		if SELL_PCT != 1:
			sell_volume = row.m_nCanUseVolume*SELL_PCT//10*10
		else:
			sell_volume = row.m_nCanUseVolume
			
		print(index,'Profit Level:',CURRENT_ACTIVE_THRESHOLD,'卖出：',SELL_PCT,sell_volume)
	
		# 判断是否触发止盈条件
		cond = (row['max_pct_chg'] - row['pct_chg']) > TAKE_PROFIT_DRAWDOWN # 从最大回撤跌幅超过2%后激活
		cond &= row['max_pct_chg'] > CURRENT_ACTIVE_THRESHOLD # 最大涨幅超过阈值后激活
		cond &= row['pct_chg'] > TAKE_PROFIT_DEAL_THRESHOLD # 执行止盈的最小涨幅，小于此涨幅，不执行止盈，优先级在触发止盈之上
		
		
		#如果满足止盈条件，执行卖出操作,7-买二价下单
		if cond:
			remark = '策略回落止盈'
			passorder(24, 1101, ACCOUNT, index, 7, 0, sell_volume, __name__, 2, remark, C)
			logging.debug(f'\n{row["name"]} 止盈,卖出委托: {row["close"]}')
			#记录最新的止盈级别
			# 首先找到对应的行索引
			matching_indices = profit_level_df.index[profit_level_df['code'] == index]
			# 然后对这些行的 'level' 值进行增加
			for idx in matching_indices:
				profit_level_df.at[idx, 'level'] += 1
			
			
'''
	# 批量止盈
	df['target_price'] = df['close'] * 0.95
	df['remark'] = '动态止盈单'
	df.apply(
		lambda row: passorder(24, 1101, ACCOUNT, row.name, 11, row.target_price, row.m_nCanUseVolume, __name__, 2, row.remark, C),
		axis=1
	)
'''

# 初始化函数
def init(C: object):
	logging.info(f"\n /\_/\ \n( o.o )\n > ^ <\ninit 【Whac-A-Mole callback version】\nDesigned by https://lude.cc")
	
	# 设置日志等级
	LOG_LEVEL = getattr(logging, LOG_LEVEL_STR)
	logging.basicConfig(format='\n【%(levelname)s】%(message)s\n', level=logging.DEBUG)
	logging.getLogger().setLevel(LOG_LEVEL)

	global ACCOUNT
	ACCOUNT = account if 'account' in globals() else ACCOUNT # 图形界面赋值ACCOUNT
	f = partial(callback_handle, C) # 将C传入callback_handle
	C.set_account(ACCOUNT) # 运行持仓回调需要此步骤
	
	global pos_dicts # 调用全局持仓字典
	position_info = get_trade_detail_data(ACCOUNT, 'stock', 'position') # 获取持仓对象
	pos_dicts = {item.pop('code'): item for item in map(position_to_dict, position_info) if item['m_nVolume'] > 0} # 将持仓量大于0的持仓对象转换为dict[str, dict]的迭代对象
	#2024/5/16 增加多级止盈
	#获取初始持仓赋值给globa 止盈记录df
	global profit_level_df
	#获取持仓
	code_list = list(pos_dicts.keys())
	profit_level_df['code'] = code_list
	#初始化止盈级别,初始0 为第一级止盈
	profit_level_df['level'] = 0
	
	logging.info(f'\n初始化持仓:\n{DataFrame.from_dict(pos_dicts, orient="index")}')
	logging.info(f'\n初始化止盈级别:\n{profit_level_df}')
	
	C.subscribe_whole_quote(['SH', 'SZ'], f) # 订阅全推数据并挂载回调函数


# 持仓回调，更新持仓，每次传入一个positonInfo
def position_callback(C: object, positonInfo: object):
	global pos_dicts # 调用全局持仓字典
	pos_dict = position_to_dict(positonInfo) # 将持仓对象position转为dict
	logging.debug(f'持仓更新项:\n{DataFrame([pos_dict])}')
	code = pos_dict.pop('code') # 从字典里弹出code
	# 若更新标的总量为0且code在全局持仓中，则从全局持仓字典中此持仓信息
	if (pos_dict['m_nVolume']==0) and (code in pos_dicts.keys()): 
		pos_dicts.pop(code)
	# 若更新标的总量不为0且code不在全局持仓中，则将此持仓信息加入全局持仓字典中
	elif (pos_dict['m_nVolume']!=0) and (code not in pos_dicts.keys()):
		pos_dicts[code] = pos_dict
	# 若更新标的总量不为0则更新全局持仓字典中的code项数据
	elif (pos_dict['m_nVolume']!=0): 
		pos_dicts[code].update(pos_dict) 
	logging.debug(f'更新后全局持仓:\n{DataFrame.from_dict(pos_dicts, orient="index")}')

# 委托回调，打印日志，每次传入一个orderInfo
def order_callback(C: object, orderInfo: object):
	logging.debug(f'委托回报:\n{DataFrame([orderinfo_to_dict(orderInfo)])}')







