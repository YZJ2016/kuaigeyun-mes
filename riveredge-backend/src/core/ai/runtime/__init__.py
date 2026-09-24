"""LangChain 运行时适配层（KR-D3/D5，设计 §6）。

分层规则：本包只放与业务无关的 LangChain 适配，被 ``apps/*`` 依赖；
禁止反向 import ``apps.*``（目录行解析对 ``apps.kuaiai.models.catalog``
用惰性 try/ImportError，属单向消费）。
"""
