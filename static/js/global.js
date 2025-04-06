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
    // 阻止默认提交
    event.preventDefault();

    // 创建隐藏字段容器
    const hiddenFields = document.createElement('div');

    // 添加精确匹配状态
    const exactMatch = document.getElementById('exact_match').checked;
    if (exactMatch) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'exact_match';
        input.value = 'on';
        hiddenFields.appendChild(input);
    }

    // 添加自然语言搜索状态
    const nlpMatch = document.getElementById('nlp_match').checked;
    if (nlpMatch) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'nlp_match';  // 注意这里改为与Flask代码一致的名称
        input.value = 'on';
        hiddenFields.appendChild(input);
    }

    // 将隐藏字段添加到表单
    this.appendChild(hiddenFields);

    // 手动提交表单
    this.submit();
});
// Show the input area when the + button is clicked
function showTagInput(imageId) {
    // Show the input area and focus the input field
    document.getElementById('tag-input-area-' + imageId).classList.remove('hidden');
    document.getElementById('new-tag-input-' + imageId).focus();

    // Hide the + button
    document.getElementById('add-tag-btn-' + imageId).classList.add('opacity-0');
    document.getElementById('add-tag-btn-' + imageId).classList.add('hidden');
    document.getElementById('add-tag-btn-' + imageId).classList.remove('group-hover/tag-area:opacity-100');

    // Add event listener to close the input area when clicking outside
    document.addEventListener('click', function (event) {
        var inputArea = document.getElementById('tag-input-area-' + imageId);
        var addButton = document.getElementById('add-tag-btn-' + imageId);

        // If the click is outside the input area and the button, close the input area
        if (!inputArea.contains(event.target) && !addButton.contains(event.target)) {
            inputArea.classList.add('hidden');
            addButton.classList.remove('hidden');
            addButton.classList.add('group-hover/tag-area:opacity-100');
        }
    });
}

// Submit the tag
function submitTag(imageId) {
    const newTag = document.getElementById('new-tag-input-' + imageId).value.trim();
    // Validate the tag (only alphanumeric, Chinese characters, or non-empty)
    const tagRegex = /^[a-zA-Z0-9\u4e00-\u9fa5\s]+$/;
    if (!newTag.trim() || !tagRegex.test(newTag)) {
        alert('标签无效！请输入有效的标签。');
        return;
    }

    // Send a POST request to add the tag (pseudo code)
    fetch('/add_tag', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            image_id: imageId,
            tag: newTag
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const container = document.getElementById('image-' + imageId + '-tags');
                if (container) {
                    //copy the first tag element to create a new tag element
                    const tagElement = container.children[0].cloneNode(true);
                    tagElement.id = `tag-${newTag}-${imageId}`;
                    tagElement.children[0].innerText = newTag;
                    tagElement.children[0].setAttribute('onclick', `addTag('${newTag}')`);
                    tagElement.children[1].setAttribute('onclick', `deleteTag(${imageId}, '${newTag}')`);
                    //在倒数第一个元素之前插入新元素
                    container.insertBefore(tagElement, container.children[container.children.length - 1]);
                }
            } else {
                if (data.duplicate) {
                    alert('标签已存在，请勿重复添加');
                } else
                    alert('标签添加失败，请稍后再试');
            }
        })
        .catch(error => {
            console.error('Error adding tag:', error);
            alert('发生错误，请稍后再试');
        });

    // Clear and hide the input area
    document.getElementById('new-tag-input-' + imageId).value = '';
    document.getElementById('tag-input-area-' + imageId).classList.add('hidden');
    document.getElementById('add-tag-btn-' + imageId).classList.remove('hidden');
    document.getElementById('add-tag-btn-' + imageId).classList.add('group-hover/tag-area:opacity-100');
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