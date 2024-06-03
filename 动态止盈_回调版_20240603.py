# encoding:gbk
# Author: ��ѩʱ��
# Date: 2023-10-16
# Copyright (C) »���� lude.cc All Rights Reserved.
# �޸�Ϊ�༶ֹӯ - By ����-������
# Last modified:	2024/5/25

import logging
from functools import partial
from typing import List, Dict, Optional
from pandas import DataFrame, Series

ACCOUNT: str = '8881522601'# �����˺�
TAKE_PROFIT_ACTIVE_THRESHOLD: float = 6.5 # ����ֹӯ����С�Ƿ�(��λ%��,��ǰ�Ƿ���ȴ�ֵ�Żᴥ��ֹӯ����
TAKE_PROFIT_DRAWDOWN: float = 0.3 # ����ֹӯ��С�س�(��λ%�������س�����ڴ�ֵ�Żᴥ��ֹӯ����
TAKE_PROFIT_DEAL_THRESHOLD: float = 1 # ִ��ֹӯ����С�Ƿ�(��λ%������ǰ�Ƿ���ȴ�ֵ�Żᴥ��ֹӯ����
ONLY_CB: bool = True # �Ƿ�ֻ�Կ�תծ����ֹӯ

# ���Ա���б�������ֹӯ
IGNORE_LIST_STR: str = '000001.SZ,600000.SH' 
IGNORE_LIST: List[str] = list(map(lambda code: code.strip().upper(), IGNORE_LIST_STR.split(','))) 

# ��־�ȼ�
LOG_LEVEL_STR: str = 'DEBUG'

pos_dicts: Optional[Dict[str, Dict]] = None # ȫ�ֲֳ�

#����ȫ�ֲֳֵĵ�ǰֹӯˮƽ
profit_level_df = DataFrame()

#����ÿ��ֹӯ�Ƿ���������
PROFIT_THRESHOLDS  = {
    'level': [6.3,7.5,8.5],
    'sell_pct': [0.5,0.5,1]		# lelve1 ��һ�룬level2 ��ʣ���һ�㣨1/4����level3 ȫ������
}

PROFIT_THRESHOLDS_DF = DataFrame(PROFIT_THRESHOLDS)

# ������������df
def gen_data_df(data_dict: Dict) -> DataFrame:
	
	df = DataFrame.from_dict(data_dict, dtype='float').T.reset_index().rename(columns={'index': 'code'})
	# �����ľ���
	bidPrice_columns = ['bid1','bid2','bid3','bid4','bid5']
	askPrice_columns = ['ask1','ask2','ask3','ask4','ask5']
	df[bidPrice_columns] = df['bidPrice'].apply(Series, index=bidPrice_columns)
	df[askPrice_columns] = df['askPrice'].apply(Series, index=askPrice_columns)
	df['averagePrice'] = (df['bid1'] + df['ask1']) / 2
	df.loc[(df['bid1'] == 0) | (df['ask1'] == 0),'averagePrice'] = df['bid1'] + df['ask1'] # �ǵ�ͣ����

	df.rename(columns={'averagePrice': 'close', 'lastClose': 'pre_close','volume':'vol'}, inplace=True)
	df['amount'] = df['amount'] / 1e4
	df = df[(df.close != 0) & (df.high !=0)] # �ּ۴���1�ı��

	# ��������ָ��
	df['pct_chg'] = ((df.close / df.pre_close - 1) * 100)
	df['max_pct_chg'] = ((df.high / df.pre_close - 1) * 100)
    
	# չʾ��
	display_columns = ['code', 'close', 'pct_chg', 'max_pct_chg', 'high', 'low', 'pre_close', 'vol', 'amount']
	df = df[display_columns]
	return df

# ���ֲֶ���positionӳ��Ϊdict(�����ֶβο�:http://docs.thinktrader.net/pages/e148c4/#_5-3-4-position-%E6%8C%81%E4%BB%93%E5%AF%B9%E8%B1%A1)
def position_to_dict(position: object) -> Dict:
	return {
		'code': position.m_strInstrumentID + '.' + position.m_strExchangeID, # ֤ȯ���� 000001.SZ
		'name': position.m_strInstrumentName, # ֤ȯ����
		'm_nVolume': position.m_nVolume, # ��ǰӵ�ɣ��ֲ���
		'm_nCanUseVolume': position.m_nCanUseVolume, # ���������óֲ֣��ڻ���������ֶΣ���Ʊ�Ŀ�������
		'm_dMarketValue': position.m_dMarketValue, # ��ֵ����Լ��ֵ
		'm_dPositionCost': position.m_dPositionCost, # �ֲֳɱ�����Ʊ����Ҫ
		'm_dPositionProfit': position.m_dPositionProfit, # �ֲ�ӯ������Ʊ����Ҫ
		'm_dFloatProfit': position.m_dFloatProfit, # ����ӯ������ǰ�� * ����ǰ�� - ���ּۣ� * ��Լ��������ƱΪ 1��
	}

# ��ί�ж���orderInfoӳ��Ϊdict(�����ֶβο�:http://docs.thinktrader.net/pages/e148c4/#_5-3-2-order-%E5%A7%94%E6%89%98%E5%AF%B9%E8%B1%A1)
def orderinfo_to_dict(orderinfo: object) -> Dict:
	return {
		'code': orderinfo.m_strInstrumentID + '.' + orderinfo.m_strExchangeID, # ֤ȯ���� 000001.SZ
		'name': orderinfo.m_strInstrumentName, # ֤ȯ����
		'm_dLimitPrice': orderinfo.m_dLimitPrice, # ί�м۸�
		'm_nVolumeTotalOriginal': orderinfo.m_nVolumeTotalOriginal, # ί������
		'm_nOffsetFlag': orderinfo.m_nOffsetFlag, # ��������
	}

# ����ȫ�ƻص�����
def callback_handle(C: object, data: Dict[str, Dict]) -> None:
	global pos_dicts # ����ȫ�ֲֳ��ֵ�
	global profit_level_df	#ȫ��ֹӯ��¼
	
	pos_code = pos_dicts.keys() # �ֱֲ��list
	if ONLY_CB: # �Ƿ�ֻ�����ڿ�תծ
		pos_code = set(filter(lambda x: x.startswith(('11', '12')), pos_code))
	data_code = data.keys() # ���ı��list
	codes = pos_code & data_code #�ֱֲ�ĺͶ��ı�ĵ��غϱ��
	# �����غϣ����˳�
	if not codes:
		return
	# ��������df
	data_dict = {code: data[code] for code in codes}
	data_df = gen_data_df(data_dict).set_index('code')
	# ���ɳֲ�df
	pos_df = DataFrame.from_dict(pos_dicts, orient='index')
	# �ϲ��ֲ����ݺ���������
	df = pos_df[['name', 'm_nCanUseVolume', 'm_nVolume']].merge(data_df[['pct_chg', 'max_pct_chg', 'close']], how='inner', left_index=True, right_index=True)
	
	logging.debug(f'\n����ص�������:\n{df}')
	
	#2024/5/16 ��Ϊ�༶ֹӯ
	
	#��ȡ���λص��Ĵ���
	codes = df.index.tolist()
	#print('\n����ص�codes:\n',codes)
	
	for index, row in df.iterrows():
		
		#��ȡ��ǰ��ĵ�ǰֹӯ������Ƿ�
		i = profit_level_df.loc[profit_level_df['code'] == index, 'level'].values[0]
		
		if i < PROFIT_THRESHOLDS_DF.shape[0]:
			CURRENT_ACTIVE_THRESHOLD = PROFIT_THRESHOLDS_DF.iloc[i]['level']
		else:
				logging.debug(f'\n�����⣬���ɣ�����:\n{row}')
				return
				
		#����ֹӯ���������������
		SELL_PCT = PROFIT_THRESHOLDS_DF.iloc[i]['sell_pct']
		if SELL_PCT != 1:
			sell_volume = row.m_nCanUseVolume*SELL_PCT//10*10
		else:
			sell_volume = row.m_nCanUseVolume
			
		print(index,'Profit Level:',CURRENT_ACTIVE_THRESHOLD,'������',SELL_PCT,sell_volume)
	
		# �ж��Ƿ񴥷�ֹӯ����
		cond = (row['max_pct_chg'] - row['pct_chg']) > TAKE_PROFIT_DRAWDOWN # �����س���������2%�󼤻�
		cond &= row['max_pct_chg'] > CURRENT_ACTIVE_THRESHOLD # ����Ƿ�������ֵ�󼤻�
		cond &= row['pct_chg'] > TAKE_PROFIT_DEAL_THRESHOLD # ִ��ֹӯ����С�Ƿ���С�ڴ��Ƿ�����ִ��ֹӯ�����ȼ��ڴ���ֹӯ֮��
		
		
		#�������ֹӯ������ִ����������,7-������µ�
		if cond:
			remark = '���Ի���ֹӯ'
			passorder(24, 1101, ACCOUNT, index, 7, 0, sell_volume, __name__, 2, remark, C)
			logging.debug(f'\n{row["name"]} ֹӯ,����ί��: {row["close"]}')
			#��¼���µ�ֹӯ����
			# �����ҵ���Ӧ��������
			matching_indices = profit_level_df.index[profit_level_df['code'] == index]
			# Ȼ�����Щ�е� 'level' ֵ��������
			for idx in matching_indices:
				profit_level_df.at[idx, 'level'] += 1
			
			
'''
	# ����ֹӯ
	df['target_price'] = df['close'] * 0.95
	df['remark'] = '��ֹ̬ӯ��'
	df.apply(
		lambda row: passorder(24, 1101, ACCOUNT, row.name, 11, row.target_price, row.m_nCanUseVolume, __name__, 2, row.remark, C),
		axis=1
	)
'''

# ��ʼ������
def init(C: object):
	logging.info(f"\n /\_/\ \n( o.o )\n > ^ <\ninit ��Whac-A-Mole callback version��\nDesigned by https://lude.cc")
	
	# ������־�ȼ�
	LOG_LEVEL = getattr(logging, LOG_LEVEL_STR)
	logging.basicConfig(format='\n��%(levelname)s��%(message)s\n', level=logging.DEBUG)
	logging.getLogger().setLevel(LOG_LEVEL)

	global ACCOUNT
	ACCOUNT = account if 'account' in globals() else ACCOUNT # ͼ�ν��渳ֵACCOUNT
	f = partial(callback_handle, C) # ��C����callback_handle
	C.set_account(ACCOUNT) # ���гֲֻص���Ҫ�˲���
	
	global pos_dicts # ����ȫ�ֲֳ��ֵ�
	position_info = get_trade_detail_data(ACCOUNT, 'stock', 'position') # ��ȡ�ֲֶ���
	pos_dicts = {item.pop('code'): item for item in map(position_to_dict, position_info) if item['m_nVolume'] > 0} # ���ֲ�������0�ĳֲֶ���ת��Ϊdict[str, dict]�ĵ�������
	#2024/5/16 ���Ӷ༶ֹӯ
	#��ȡ��ʼ�ֲָ�ֵ��globa ֹӯ��¼df
	global profit_level_df
	#��ȡ�ֲ�
	code_list = list(pos_dicts.keys())
	profit_level_df['code'] = code_list
	#��ʼ��ֹӯ����,��ʼ0 Ϊ��һ��ֹӯ
	profit_level_df['level'] = 0
	
	logging.info(f'\n��ʼ���ֲ�:\n{DataFrame.from_dict(pos_dicts, orient="index")}')
	logging.info(f'\n��ʼ��ֹӯ����:\n{profit_level_df}')
	
	C.subscribe_whole_quote(['SH', 'SZ'], f) # ����ȫ�����ݲ����ػص�����


# �ֲֻص������³ֲ֣�ÿ�δ���һ��positonInfo
def position_callback(C: object, positonInfo: object):
	global pos_dicts # ����ȫ�ֲֳ��ֵ�
	pos_dict = position_to_dict(positonInfo) # ���ֲֶ���positionתΪdict
	logging.debug(f'�ֲָ�����:\n{DataFrame([pos_dict])}')
	code = pos_dict.pop('code') # ���ֵ��ﵯ��code
	# �����±������Ϊ0��code��ȫ�ֲֳ��У����ȫ�ֲֳ��ֵ��д˳ֲ���Ϣ
	if (pos_dict['m_nVolume']==0) and (code in pos_dicts.keys()): 
		pos_dicts.pop(code)
	# �����±��������Ϊ0��code����ȫ�ֲֳ��У��򽫴˳ֲ���Ϣ����ȫ�ֲֳ��ֵ���
	elif (pos_dict['m_nVolume']!=0) and (code not in pos_dicts.keys()):
		pos_dicts[code] = pos_dict
	# �����±��������Ϊ0�����ȫ�ֲֳ��ֵ��е�code������
	elif (pos_dict['m_nVolume']!=0): 
		pos_dicts[code].update(pos_dict) 
	logging.debug(f'���º�ȫ�ֲֳ�:\n{DataFrame.from_dict(pos_dicts, orient="index")}')

# ί�лص�����ӡ��־��ÿ�δ���һ��orderInfo
def order_callback(C: object, orderInfo: object):
	logging.debug(f'ί�лر�:\n{DataFrame([orderinfo_to_dict(orderInfo)])}')







