function toggleDarkMode() {
    document.documentElement.classList.toggle('dark');
    
    fetch('/toggle_darkmode', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        console.log('Dark mode is now:', data.darkmode);
    })
    .catch(error => {
        console.error('Error:', error);
    });
}

//添加标签到搜索框
function addTag(seltags) {
    const input = document.getElementById('tags');
    if (input.value !== '' && input.value[input.value.length - 1] !== ',') {
        input.value += ',';
    }
    input.value += seltags;
    toggleClearIcon();
    input.focus();
}

document.getElementById('searchForm').addEventListener('submit', function (event) {
    event.preventDefault(); // 阻止默认提交

    // 获取搜索词
    const searchTerm = document.getElementById('tags').value.trim();
    if (!searchTerm) return; // 如果搜索词为空，不跳转

    // 获取复选框状态
    const exactMatch = document.getElementById('exact_match').checked;
    const nlpMatch = document.getElementById('nlp_match').checked;
    const submitButton = this.querySelector('button[type="submit"]');
    if (nlpMatch) {
        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.innerHTML = `
            <svg class="animate-spin w-5 text-gray-800" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        `;
        submitButton.disabled = true;
        const loadingText = document.createElement('div');
        loadingText.id = 'nlp-loading';
        loadingText.className = 'w-full text-center mt-2 text-sm text-gray-700 dark:text-gray-200';
        loadingText.textContent = '正在处理自然语言搜索，这可能需要一些时间...';

        // 插入到搜索容器底部（搜索框外部）
        const searchContainer = document.getElementById('searchContainer');
        searchContainer.appendChild(loadingText);
    }
    // 构建查询参数
    const params = new URLSearchParams();
    params.append('tags', searchTerm);
    if (exactMatch) params.append('exact_match', 'on');
    if (nlpMatch) params.append('nlp_match', 'on');

    // 跳转到目标 URL（如 /search?tags=xxx&exact_match=on&nlp_match=on）
    window.location.href = `/search/?${params.toString()}`;
});
// Show the input area when the + button is clicked
// 全局变量，用于跟踪当前活动的关闭函数
let activeCloseListener = null;

// 修正后的 showTagInput 函数
function showTagInput(imageId) {
    const inputArea = document.getElementById('tag-input-area-' + imageId);
    const addButton = document.getElementById('add-tag-btn-' + imageId);
    const newTagInput = document.getElementById('new-tag-input-' + imageId);

    // 如果之前有活动的监听器，先移除它
    if (activeCloseListener) {
        document.removeEventListener('click', activeCloseListener);
    }

    // 显示输入区域并聚焦
    inputArea.classList.remove('hidden');
    newTagInput.focus();

    // 隐藏"+"按钮
    addButton.classList.add('hidden');

    // 定义一个具名的关闭函数，以便我们之后可以移除它
    const handleClickOutside = (event) => {
        // 如果点击发生在输入区域或添加按钮之外
        if (!inputArea.contains(event.target) && !addButton.contains(event.target)) {
            inputArea.classList.add('hidden');
            addButton.classList.remove('hidden');
            // **【核心修复】** 移除监听器，避免内存泄漏和重复绑定
            document.removeEventListener('click', handleClickOutside);
            activeCloseListener = null; // 清空引用
        }
    };

    // 添加新的监听器
    document.addEventListener('click', handleClickOutside);
    // 保存对当前监听器的引用
    activeCloseListener = handleClickOutside;
}


// Submit the tag
function submitTag(imageId) {
    const newTagInput = document.getElementById('new-tag-input-' + imageId);
    const newTag = newTagInput.value.trim();

    // 验证标签
    const tagRegex = /^[a-zA-Z0-9\u4e00-\u9fa5\s]+$/;
    if (!newTag || !tagRegex.test(newTag)) {
        alert('标签无效！请输入有效的标签。');
        return;
    }

    fetch('/add_tag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: imageId, tag: newTag })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const container = document.getElementById('image-' + imageId + '-tags');
                if (container) {
                    // **【核心修复】**
                    // 1. 使用模板字符串定义新标签的HTML结构，确保结构始终正确
                    const newTagHTML = `
                    <div id="tag-${newTag}-${imageId}" class="flex items-center justify-center relative group/tag-content">
                        <span class="bg-white h-9 w-auto hover:bg-gray-200 cursor-pointer dark:bg-gray-600 dark:hover:bg-gray-500 smooth--trans text-black dark:text-white px-3 rounded-full text-base font-medium flex justify-center items-center relative"
                              onclick="addTag('${newTag}')">${newTag}</span>
                        <button class="absolute -top-2.5 -right-3 flex h-full items-center pr-1 pl-0.5 hidden group-hover/tag-content:block"
                                onclick="deleteTag(${imageId}, '${newTag}')">
                            <svg class="w-5 fill-gray-400 text-gray-600 hover:text-gray-600 hover:fill-gray-300 transition-colors duration-300"
                                 xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                            </svg>
                        </button>
                    </div>`;

                    // 2. 创建一个临时div来将字符串转换为DOM元素
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = newTagHTML.trim();
                    const newTagElement = tempDiv.firstElementChild;

                    // 3. 在“添加”按钮（也就是最后一个元素）之前插入这个新创建的标签
                    container.insertBefore(newTagElement, container.lastElementChild);
                }
            } else {
                if (data.duplicate) {
                    alert('标签已存在，请勿重复添加');
                } else {
                    alert('标签添加失败，请稍后再试');
                }
            }
        })
        .catch(error => {
            console.error('Error adding tag:', error);
            alert('发生错误，请稍后再试');
        });

    // 清理并隐藏输入区域
    newTagInput.value = '';
    const inputArea = document.getElementById('tag-input-area-' + imageId);
    const addButton = document.getElementById('add-tag-btn-' + imageId);
    inputArea.classList.add('hidden');
    addButton.classList.remove('hidden');
    addButton.classList.add('group-hover/tag-area:opacity-100');

    if (activeCloseListener) {
        document.removeEventListener('click', activeCloseListener);
        activeCloseListener = null;
    }
}

function deleteTag(imageID, tagName) {
    //add a confirm dialog
    if (!confirm(`确定要删除标签'${tagName}'吗？`)) {
        return;
    }
    fetch('/remove_tag', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            image_id: imageID,
            tag: tagName
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove the tag from the displayed tags
                const tagElement = document.getElementById(`tag-${tagName}-${imageID}`);
                tagElement.remove();
            } else {
                alert('删除标签失败，请稍后再试');
            }
        })
        .catch(error => {
            console.error('Error deleting tag:', error);
            alert('发生错误，请稍后再试');
        });
}


function toggleClearIcon() {
    const input = document.getElementById('tags');
    const clearIcon = document.getElementById('clear-icon');
    if (input.value.trim() !== '') {
        clearIcon.classList.remove('hidden'); // 显示清除图标
    } else {
        clearIcon.classList.add('hidden'); // 隐藏清除图标
    }
}

window.onload = function(){
    // 在页面加载时检查输入框是否为空
    toggleClearIcon();
};
function clearInput() {
    const input = document.getElementById('tags');
    input.value = ''; // 清空输入框
    toggleClearIcon(); // 更新清除图标的显示状态
    input.focus(); // 将焦点返回到输入框
}

function toggleLike(imageID) {
    const heartIcon = document.getElementById('heart-' + imageID);
    const heartButton = document.getElementById('like-btn-' + imageID);
    if (heartIcon.src.includes('heart.svg')) {
        heartIcon.src = '../static/imgs/heart-filled.svg';
        heartButton.classList.remove('opacity-0');
        heartIcon.classList.replace('hover:opacity-50', 'hover:opacity-80');
        // heartButton.classList.remove('group-hover:block');
    } else {
        heartIcon.src = '../static/imgs/heart.svg';
        heartButton.classList.add('opacity-0');
        heartButton.classList.add('group-hover:opacity-100');
        heartIcon.classList.replace('hover:opacity-80', 'hover:opacity-50');
    }
    // 发送POST请求到Flask后台
    console.log("Toggling like for image:", imageID);
    fetch('/toggle_like', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            image_id: imageID  // 向后端传递图片的ID
        })
    })
        .then(response => response.json())  // 假设后端返回JSON响应
        .then(data => {
            console.log("Response from server:", data);
            if (!data.success) {
                alert('操作失败，请稍后再试');
            }
        })
        .catch(error => {
            console.error('Error toggling like:', error);
            alert('发生错误，请稍后再试');
        });
}