"""
API 管理器使用示例

展示如何使用智能 API 管理器进行多模型调用、健康检查和故障转移。
"""

from src.api_manager import APIManger, RotationStrategy, print_status_table


def example_basic_usage():
    """基础使用示例"""
    print("\n【示例 1：基础使用】")

    manager = APIManger()

    # 获取状态
    status = manager.get_status()
    print(f"已注册 {status['total_nodes']} 个 API 节点")
    print(f"健康节点: {status['healthy_nodes']} 个")

    # 打印状态表格
    print_status_table(manager)


def example_rotation_strategies():
    """轮换策略示例"""
    print("\n【示例 2：轮换策略】")

    manager = APIManger()

    strategies = [
        RotationStrategy.ROUND_ROBIN,
        RotationStrategy.WEIGHTED_RANDOM,
        RotationStrategy.HEALTH_BASED,
        RotationStrategy.FASTEST_FIRST,
    ]

    for strategy in strategies:
        manager.config.rotation_strategy = strategy
        node = manager.select_node()
        if node:
            print(f"  {strategy.value:20s} -> {node.config.model_name}")


def example_health_check():
    """健康检查示例"""
    print("\n【示例 3：健康检查】")

    manager = APIManger()

    # 批量健康检查
    print("开始批量健康检查...")
    results = manager.health_check_batch(batch_size=5)

    healthy = sum(1 for v in results.values() if v)
    print(f"检查结果: {healthy}/{len(results)} 个节点健康")

    # 获取最佳节点
    print("\nTop 5 表现最好的节点:")
    top_nodes = manager.get_top_nodes(n=5, sort_by="success_rate")
    for i, node in enumerate(top_nodes, 1):
        print(f"  {i}. {node['model']:<25} 成功率: {node['success_rate']:.1%}  延迟: {node['avg_response_time_ms']:.0f}ms")


def example_call_with_fallback():
    """带故障转移的调用示例"""
    print("\n【示例 4：带故障转移的调用】")

    manager = APIManger()

    try:
        # 调用 API（自动故障转移）
        response = manager.call(
            messages=[{"role": "user", "content": "Say hello in one word"}],
            max_tokens=10,
            temperature=0
        )

        if response and response.choices:
            content = response.choices[0].message.content
            print(f"响应: {content}")

            # 查看使用了哪个节点
            status = manager.get_status()
            for name, node in status['nodes'].items():
                if node['total_requests'] > 0:
                    print(f"  节点 {name} 被调用 {node['total_requests']} 次")

    except Exception as e:
        print(f"调用失败: {e}")


def example_dynamic_management():
    """动态管理示例"""
    print("\n【示例 5：动态管理节点】")

    from config import LLMConfig

    manager = APIManger()

    # 添加新节点
    new_config = LLMConfig(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model_name="test-model"
    )
    manager.add_node(new_config)
    print(f"添加节点后总数: {manager.get_status()['total_nodes']}")

    # 移除节点
    manager.remove_node("test-model")
    print(f"移除节点后总数: {manager.get_status()['total_nodes']}")


def example_performance_comparison():
    """性能对比示例"""
    print("\n【示例 6：性能对比】")

    manager = APIManger()

    # 按不同指标排序
    print("\nTop 5 成功率最高的节点:")
    for node in manager.get_top_nodes(n=5, sort_by="success_rate"):
        print(f"  {node['model']:<25} 成功率: {node['success_rate']:.1%}")

    print("\nTop 5 响应最快的节点:")
    for node in manager.get_top_nodes(n=5, sort_by="response_time"):
        print(f"  {node['model']:<25} 延迟: {node['avg_response_time_ms']:.0f}ms")

    print("\nTop 5 调用最多的节点:")
    for node in manager.get_top_nodes(n=5, sort_by="requests"):
        print(f"  {node['model']:<25} 调用: {node['total_requests']} 次")


if __name__ == "__main__":
    print("=" * 80)
    print("API 管理器使用示例")
    print("=" * 80)

    example_basic_usage()
    example_rotation_strategies()
    example_health_check()
    example_call_with_fallback()
    example_dynamic_management()
    example_performance_comparison()

    print("\n所有示例运行完成！")
